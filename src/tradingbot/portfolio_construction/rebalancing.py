"""Rebalancing-Entscheidungslogik: reine Entscheidung, keine Ausführung.

Analog zu `Strategy`/`RiskManager`: `RebalancingEngine` trifft nur die
Entscheidung "welche Order-Absichten sind jetzt nötig" - die tatsächliche
Ausführung (Broker-Aufruf, Portfolio-Buchung) übernimmt die aufrufende
Backtest-Engine (`backtest/portfolio_construction_engine.py`). Komplett
getrennt vom Strategy-System - kein Zusammenspiel mit TradingSignal/
TradingOrchestrator in dieser Phase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradingbot.data.models import MarketCandle
from tradingbot.portfolio.models import PortfolioStatus
from tradingbot.portfolio_construction.constraints import PortfolioConstraints
from tradingbot.portfolio_construction.models import RebalancingTrade
from tradingbot.portfolio_construction.target_allocation import TargetAllocationPolicy


class RebalancingTrigger(ABC):
    """Entscheidet, ob an einem gegebenen Zeitschritt rebalanciert wird."""

    @abstractmethod
    def should_rebalance(
        self,
        step_index: int,
        current_weights: dict[str, float],
        target_weights: dict[str, float],
    ) -> bool:
        ...


class PeriodicTrigger(RebalancingTrigger):
    """Löst alle `every_n_steps` Zeitschritte aus (Zeitschritt 0 eingeschlossen)."""

    def __init__(self, every_n_steps: int) -> None:
        self._every_n_steps = every_n_steps

    def should_rebalance(
        self,
        step_index: int,
        current_weights: dict[str, float],
        target_weights: dict[str, float],
    ) -> bool:
        return self._every_n_steps > 0 and step_index % self._every_n_steps == 0


class DriftTrigger(RebalancingTrigger):
    """Löst aus, sobald irgendein Asset-Gewicht um mehr als
    `max_drift_percent` (in Prozentpunkten) vom Zielgewicht abweicht.
    """

    def __init__(self, max_drift_percent: float) -> None:
        self._max_drift_percent = max_drift_percent

    def should_rebalance(
        self,
        step_index: int,
        current_weights: dict[str, float],
        target_weights: dict[str, float],
    ) -> bool:
        for symbol, target in target_weights.items():
            current = current_weights.get(symbol, 0.0)
            if abs(current - target) * 100 > self._max_drift_percent:
                return True
        return False


class RebalancingEngine:
    """Kombiniert Ziel-Allokations-Policy, Constraints und Trigger zu
    konkreten Rebalancing-Order-Absichten.

    `policy` ist bewusst ein öffentliches Attribut - die aufrufende
    Backtest-Engine liest die Ziel-Gewichte separat für ihre eigene
    `allocation_history`-Aufzeichnung aus (siehe
    `portfolio_construction_engine.py`).
    """

    def __init__(
        self,
        policy: TargetAllocationPolicy,
        constraints: PortfolioConstraints,
        trigger: RebalancingTrigger,
    ) -> None:
        self.policy = policy
        self.constraints = constraints
        self.trigger = trigger

    def generate_rebalancing_orders(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        current_prices: dict[str, float],
        portfolio_status: PortfolioStatus,
        step_index: int,
    ) -> list[RebalancingTrade]:
        """Erzeugt Order-**Absichten** (keine ausgeführten Trades), um die
        aktuellen Positionen auf die (constraint-geprüften) Zielgewichte der
        Policy zurückzuführen.

        Gibt eine leere Liste zurück, wenn der Trigger nicht auslöst oder
        keine Anpassung nötig ist (Abweichung kleiner als eine minimale
        Toleranz, um Rundungs-Mikro-Orders zu vermeiden).
        """

        target_weights, _adjustments = self.constraints.apply(
            self.policy.target_weights(candles_by_symbol, portfolio_status)
        )

        total_value = portfolio_status.total_value(current_prices)
        positions_by_symbol = {p.symbol: p for p in portfolio_status.positions}

        current_weights: dict[str, float] = {}
        current_values: dict[str, float] = {}
        for symbol in candles_by_symbol:
            position = positions_by_symbol.get(symbol)
            value = position.value(current_prices[symbol]) if position else 0.0
            current_values[symbol] = value
            current_weights[symbol] = value / total_value if total_value else 0.0

        if not self.trigger.should_rebalance(step_index, current_weights, target_weights):
            return []

        orders: list[RebalancingTrade] = []
        for symbol in candles_by_symbol:
            target_value = target_weights.get(symbol, 0.0) * total_value
            delta_value = target_value - current_values[symbol]
            if abs(delta_value) < 1e-9:
                continue

            price = current_prices[symbol]
            orders.append(
                RebalancingTrade(
                    symbol=symbol,
                    side="BUY" if delta_value > 0 else "SELL",
                    quantity=abs(delta_value) / price,
                    price=price,
                )
            )

        return orders
