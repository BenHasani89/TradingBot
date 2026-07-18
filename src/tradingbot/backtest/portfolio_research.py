"""Portfolio-Construction-Research: mehrere Rebalancing-Konfigurationen auf
identischer Datenbasis testen.

Reine Orchestrierung des bereits vorhandenen `PortfolioConstructionEngine` -
keine neue Simulationslogik, keine externen Bibliotheken. Anders als
`Strategy`-Instanzen sind `RebalancingEngine`-Konfigurationen (Policy +
Constraints + Trigger) zustandslos, daher können fertige, wiederverwendbare
Instanzen direkt entgegengenommen werden - kein Klasse+Parameter-Muster wie
bei `MultiAssetResearchRunner` nötig.
"""

from __future__ import annotations

from tradingbot.backtest.portfolio_comparison import (
    PortfolioComparisonRow,
    compare_portfolio_configurations,
)
from tradingbot.backtest.portfolio_construction_engine import (
    PortfolioConstructionEngine,
    PortfolioConstructionResult,
)
from tradingbot.data.models import MarketCandle
from tradingbot.portfolio_construction.rebalancing import RebalancingEngine


class PortfolioResearchRunner:
    """Testet mehrere Rebalancing-Konfigurationen auf denselben historischen
    Kerzen."""

    def __init__(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        initial_capital: float,
    ) -> None:
        self._candles_by_symbol = candles_by_symbol
        self._initial_capital = initial_capital

    def run_raw(
        self,
        configurations: dict[str, RebalancingEngine],
    ) -> dict[str, PortfolioConstructionResult]:
        """Führt für jede benannte Konfiguration eine eigene, isolierte
        Simulation aus.

        Args:
            configurations: Zuordnung von Konfigurations-Name zu
                `RebalancingEngine`. Dieselbe Instanz kann unbedenklich für
                mehrere Konfigurationen wiederverwendet werden, da
                `RebalancingEngine` (Policy + Constraints + Trigger)
                zustandslos ist - jede Simulation bekommt trotzdem ein
                eigenes, frisches Portfolio.

        Returns:
            Zuordnung von Konfigurations-Name zu `PortfolioConstructionResult`.
        """

        results: dict[str, PortfolioConstructionResult] = {}

        for name, rebalancing_engine in configurations.items():
            engine = PortfolioConstructionEngine(
                candles_by_symbol=self._candles_by_symbol,
                rebalancing_engine=rebalancing_engine,
                initial_capital=self._initial_capital,
            )
            results[name] = engine.run()

        return results

    def run(
        self,
        configurations: dict[str, RebalancingEngine],
    ) -> list[PortfolioComparisonRow]:
        """Führt für jede benannte Konfiguration eine eigene, isolierte
        Simulation aus und liefert eine Vergleichstabelle.

        Returns:
            Eine Vergleichszeile je Konfiguration (über
            `compare_portfolio_configurations()`), in derselben Reihenfolge
            wie `configurations`.
        """

        return compare_portfolio_configurations(self.run_raw(configurations))
