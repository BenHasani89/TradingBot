"""Gemeinsame, kleine Hilfsfunktionen für die Backtest-Auswertung.

Rein additiv - keine bestehende Datei muss diese Funktionen importieren oder
sich ändern. Neuer Code (z. B. `research_report.py`) nutzt sie, um dieselbe
Formel nicht ein weiteres Mal zu duplizieren.
"""

from __future__ import annotations

from typing import Protocol

from tradingbot.backtest.models import EquityPoint


class _HasEquityCurveAndProfitLoss(Protocol):
    """Strukturelle Anforderung (kein gemeinsamer Basistyp nötig): erfüllt
    von `BacktestResult`, `PortfolioBacktestResult` und
    `PortfolioConstructionResult`, ohne dass diese davon wissen müssen."""

    equity_curve: list[EquityPoint]
    profit_loss: float


def infer_initial_capital(result: _HasEquityCurveAndProfitLoss) -> float:
    """Rekonstruiert das ursprüngliche Startkapital aus einem
    Backtest-Ergebnis.

    `profit_loss = Endwert - Startkapital`, der Endwert steckt implizit in
    `equity_curve[-1].total_value` - daraus lässt sich das Startkapital ohne
    Division exakt zurückrechnen. Gibt `0.0` zurück, wenn die Equity-Kurve
    leer ist.
    """

    if not result.equity_curve:
        return 0.0

    return result.equity_curve[-1].total_value - result.profit_loss
