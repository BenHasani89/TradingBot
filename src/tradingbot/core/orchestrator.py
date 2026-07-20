"""Trading-Orchestrierung: verbindet Marktdaten, Strategie, Risiko-Prüfung,
Order-Ausführung und Portfolio zu einem vollständigen Paper-Trading-Zyklus.
"""

from __future__ import annotations

from typing import cast

from loguru import logger

from tradingbot.core.engine import TradingEngine
from tradingbot.core.models import ExecutionCostEstimate, TradingCycleResult
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import Broker
from tradingbot.execution.models import Order, OrderSide
from tradingbot.execution.order_manager import OrderManager
from tradingbot.execution.order_repository import InMemoryOrderRepository, OrderRepository
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.base import Strategy


class TradingOrchestrator:
    """Führt einen vollständigen Paper-Trading-Zyklus aus.

    Verbindet Strategie, Risiko-Prüfung, Order-Ausführung und Portfolio-
    Buchung. Führt nur dann etwas aus, wenn die übergebene `TradingEngine`
    aktiv ist (`start()` wurde aufgerufen) - andernfalls wird kein
    Marktzugriff simuliert und kein Trade gebucht.

    Kennt ausschliesslich die `Broker`-ABC, keine konkrete Implementierung
    (`PaperBroker`, `MockLiveBroker`, künftig `LiveBroker` sind austauschbar
    - siehe `cost_estimate` unten, das genau diese Entkopplung ermöglicht).
    """

    def __init__(
        self,
        engine: TradingEngine,
        strategy: Strategy,
        risk_manager: RiskManager,
        portfolio: PortfolioManager,
        broker: Broker,
        order_repository: OrderRepository | None = None,
        cost_estimate: ExecutionCostEstimate | None = None,
    ) -> None:
        self._engine = engine
        self._strategy = strategy
        self._risk_manager = risk_manager
        self._portfolio = portfolio
        self._broker = broker
        # Additiver Injection-Punkt: bleibt `order_repository` weg (alle
        # Backtest-/Research-Aufrufer, alle bisherigen Tests), verhält sich
        # der Orchestrator exakt wie zuvor - `InMemoryOrderRepository`, kein
        # SQLite-Schreibvorgang pro simuliertem Trade. Der `OrderManager`
        # bleibt in jedem Fall im Besitz des Orchestrators und an denselben
        # `broker` gebunden wie der Cash-Check weiter unten - ein separat
        # injizierter, fertiger `OrderManager` könnte sonst versehentlich an
        # einen anderen Broker gebunden sein.
        repository = order_repository if order_repository is not None else InMemoryOrderRepository()
        self._order_manager = OrderManager(broker=broker, repository=repository)
        # Bleibt `cost_estimate` weg, entspricht das exakt dem bisherigen
        # kostenfreien Verhalten (0.0/0.0) - unabhängig vom konkreten
        # Broker, damit die Kapitalprüfung unten keine Broker-spezifischen
        # Properties mehr lesen muss (siehe ExecutionCostEstimate-Docstring).
        self._cost_estimate = (
            cost_estimate if cost_estimate is not None else ExecutionCostEstimate()
        )

    def run_cycle(self, candles: list[MarketCandle]) -> TradingCycleResult:
        """Führt einen Trading-Zyklus für die übergebenen Kerzen aus.

        Ablauf: Strategie analysiert die Kerzen -> Risiko-System prüft das
        Signal -> bei Genehmigung wird eine Order erzeugt, über den
        `OrderManager`/Broker ausgeführt und bei Erfolg im Portfolio gebucht.

        Args:
            candles: Kerzen eines einzelnen Symbols, chronologisch sortiert.
                Muss mindestens so viele Kerzen enthalten, wie die verwendete
                Strategie für eine Analyse benötigt.

        Returns:
            Ergebnis des Zyklus. `order`/`execution` sind `None`, wenn das
            Signal nicht genehmigt wurde oder - bei BUY - nicht genügend
            Kapital im Portfolio verfügbar ist (siehe
            `PortfolioManager.available_cash()`). Ein Trade kann so nie
            negatives Kapital erzeugen; der Broker wird in diesem Fall gar
            nicht erst aufgerufen.

        Raises:
            RuntimeError: wenn die `TradingEngine` nicht aktiv ist.
        """

        if not self._engine.status()["running"]:
            raise RuntimeError(
                "TradingEngine ist nicht aktiv - Zyklus wird nicht ausgeführt."
            )

        signal = self._strategy.analyze(candles)
        decision = self._risk_manager.evaluate(signal)

        if not decision.approved:
            logger.info("Zyklus ohne Order beendet: {}", decision.reason)
            return TradingCycleResult(
                signal=signal,
                decision=decision,
                order=None,
                execution=None,
                closed_trade=None,
            )

        # Das Risiko-System lehnt HOLD-Signale immer ab (siehe RiskManager),
        # daher ist an dieser Stelle ausschliesslich BUY oder SELL möglich.
        if signal.signal not in ("BUY", "SELL"):
            raise RuntimeError(
                f"Unerwartetes genehmigtes Signal ohne Handelsrichtung: {signal.signal}"
            )
        side = cast(OrderSide, signal.signal)

        current_price = candles[-1].close
        quantity = decision.position_size / current_price

        if side == "BUY":
            # Vorhersage des Kapitalbedarfs inkl. angenommener Slippage und
            # Gebühr - broker-unabhängig (siehe ExecutionCostEstimate), da
            # die Broker-ABC selbst keine Kosten-Properties kennt. Bei
            # PaperBroker mit passend konfiguriertem cost_estimate entspricht
            # das exakt dem intern berechneten Fill-Preis.
            expected_fill_price = current_price * (1 + self._cost_estimate.slippage_percent)
            required_cash = quantity * expected_fill_price * (1 + self._cost_estimate.fee_percent)
            available_cash = self._portfolio.available_cash()
            if required_cash > available_cash:
                logger.info(
                    "Zyklus ohne Order beendet: nicht genügend Kapital "
                    "(benötigt {}, verfügbar {})",
                    required_cash,
                    available_cash,
                )
                return TradingCycleResult(
                    signal=signal,
                    decision=decision,
                    order=None,
                    execution=None,
                    closed_trade=None,
                )

        order = Order(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            price=current_price,
        )

        execution = self._order_manager.submit(order)
        closed_trade = None

        if execution.success:
            filled_order = execution.order

            # Gebucht wird die tatsächlich gefüllte Menge, nicht die
            # angefragte: execution.filled_quantity ist None bei Brokern
            # ohne Teilausführungs-Unterscheidung (PaperBroker/
            # MockLiveBroker - "Legacy", siehe
            # execution.models.derive_order_status()) und entspricht dann
            # weiterhin filled_order.quantity. Ein LiveBroker mit echtem
            # Partial Fill liefert hier die reale, kleinere Menge.
            actual_quantity = (
                execution.filled_quantity
                if execution.filled_quantity is not None
                else filled_order.quantity
            )

            # Sicherheitsnetz gegen eine widersprüchliche Broker-Antwort
            # (success=True bei filled_quantity<=0): ein korrekt
            # implementierter Broker liefert in diesem Fall bereits
            # success=False (siehe execution/live_broker.py), aber dieser
            # Vertrag ist nicht auf der Broker-ABC erzwungen. Ohne diese
            # Prüfung würde effective_price weiter unten durch 0 teilen und
            # ein Trade mit Nullmenge gebucht.
            if actual_quantity <= 0:
                logger.error(
                    "Execution meldet success=True bei filled_quantity={} - "
                    "kein Trade gebucht (widersprüchliche Broker-Antwort).",
                    actual_quantity,
                )
            else:
                # Portfolio kennt weder Gebühren noch Slippage (unveränderte
                # Schnittstelle) - daher wird hier ein einzelner effektiver
                # Preis gebildet, der Fill-Preis (bereits inkl. Slippage) und
                # Gebühr zu einem korrekten Netto-Kapitaleffekt zusammenfasst.
                # Gebühr/Slippage bleiben trotzdem separat im ExecutionResult
                # sichtbar (siehe execution.fee / execution.slippage).
                #
                # Gebühr nur einrechnen, wenn ihr Asset unbekannt ist
                # (execution.fee_asset is None - Legacy, z. B. PaperBroker/
                # MockLiveBroker) oder die Gebühr exakt 0 ist (Einheit dann
                # irrelevant). Ein bekanntes, von None verschiedenes
                # fee_asset (siehe execution/live_broker.py) könnte vom
                # Quote-Asset des Symbols abweichen (z. B. Base-Asset-
                # Gebühr bei einem BUY) - ohne verlässliche Kenntnis der
                # Quote-Währung wird eine solche Gebühr NICHT blind addiert,
                # um keine unterschiedlichen Währungen zu vermischen. Sie
                # bleibt trotzdem über execution.fee/.fee_asset sichtbar,
                # nur eben nicht im Portfolio-Kapital verbucht.
                fee_is_safe_to_include = execution.fee_asset is None or execution.fee == 0.0
                included_fee = execution.fee if fee_is_safe_to_include else 0.0

                if filled_order.side == "BUY":
                    total_cash_impact = filled_order.price * actual_quantity + included_fee
                else:
                    total_cash_impact = filled_order.price * actual_quantity - included_fee
                effective_price = total_cash_impact / actual_quantity

                closed_trade = self._portfolio.apply_trade(
                    symbol=filled_order.symbol,
                    side=filled_order.side,
                    quantity=actual_quantity,
                    price=effective_price,
                )
                logger.info(
                    "Trade gebucht: {} {} {} @ {} (Fill {}, Gebühr {}, Slippage {})",
                    filled_order.side,
                    actual_quantity,
                    filled_order.symbol,
                    effective_price,
                    filled_order.price,
                    execution.fee,
                    execution.slippage,
                )

        return TradingCycleResult(
            signal=signal,
            decision=decision,
            order=order,
            execution=execution,
            closed_trade=closed_trade,
        )
