"""Vergleich mehrerer Portfolio-Construction-Ergebnisse auf identischer
Datenbasis.

Bewusst eigenständig von `backtest/comparison.py`, obwohl beide Module
strukturell ähnlich sind (Duck Typing würde technisch funktionieren, da
`PortfolioConstructionResult` dieselben vier Felder besitzt): "trades"
bedeutet bei Portfolio Construction die Anzahl ausgeführter
Rebalancing-Orders, nicht Strategy-Order-Ausführungen - eine geteilte
Funktion würde diesen Bedeutungsunterschied verschleiern.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.backtest.portfolio_construction_engine import PortfolioConstructionResult


@dataclass
class PortfolioComparisonRow:
    """Eine Zeile der Portfolio-Construction-Vergleichstabelle."""

    configuration_name: str
    rebalancing_orders: int
    profit_loss: float
    performance_percent: float
    max_drawdown_percent: float


def compare_portfolio_configurations(
    results: dict[str, PortfolioConstructionResult],
) -> list[PortfolioComparisonRow]:
    """Fasst mehrere `PortfolioConstructionResult`-Objekte zu einer
    Vergleichstabelle zusammen.

    Voraussetzung für einen fairen Vergleich: alle übergebenen Ergebnisse
    stammen aus Simulationen auf denselben historischen Kerzen mit gleichem
    Startkapital.

    Args:
        results: Zuordnung von Konfigurations-Name zum zugehörigen
            `PortfolioConstructionResult`.

    Returns:
        Eine Zeile je Konfiguration, in derselben Reihenfolge wie `results`.
    """

    return [
        PortfolioComparisonRow(
            configuration_name=name,
            rebalancing_orders=result.trades,
            profit_loss=result.profit_loss,
            performance_percent=result.performance_percent,
            max_drawdown_percent=result.max_drawdown_percent,
        )
        for name, result in results.items()
    ]
