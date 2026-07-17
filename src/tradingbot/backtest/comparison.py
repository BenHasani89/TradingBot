"""Vergleich mehrerer Backtest-Ergebnisse auf identischer Datenbasis.

Reine Auswertungsfunktion: fasst bereits vorhandene `BacktestResult`-Objekte
zu einer strukturierten Vergleichstabelle zusammen. Ändert nichts an
bestehenden Backtest- oder Strategie-Klassen.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.backtest.models import BacktestResult


@dataclass
class ComparisonRow:
    """Eine Zeile der Strategie-Vergleichstabelle."""

    strategy_name: str
    trades: int
    profit_loss: float
    performance_percent: float
    max_drawdown_percent: float


def compare_strategies(results: dict[str, BacktestResult]) -> list[ComparisonRow]:
    """Fasst mehrere `BacktestResult`-Objekte zu einer Vergleichstabelle zusammen.

    Voraussetzung für einen fairen Vergleich: alle übergebenen Ergebnisse
    stammen aus Backtests auf denselben historischen Kerzen mit gleichem
    Startkapital und gleichen Risiko-Einstellungen. Diese Funktion prüft das
    nicht, sondern wertet nur bereits vorliegende Ergebnisse aus.

    Args:
        results: Zuordnung von Strategie-Name zum zugehörigen `BacktestResult`.

    Returns:
        Eine Zeile je Strategie, in derselben Reihenfolge wie `results`.
    """

    return [
        ComparisonRow(
            strategy_name=name,
            trades=result.trades,
            profit_loss=result.profit_loss,
            performance_percent=result.performance_percent,
            max_drawdown_percent=result.max_drawdown_percent,
        )
        for name, result in results.items()
    ]
