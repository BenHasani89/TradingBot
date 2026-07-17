"""Reine Berechnungsfunktionen für Backtest-Kennzahlen (keine Klassen)."""

from __future__ import annotations

from tradingbot.backtest.models import EquityPoint


def performance_percent(
    initial_capital: float,
    equity_curve: list[EquityPoint],
) -> float:
    """Berechnet die Gesamtrendite in Prozent gegenüber dem Startkapital.

    Gibt 0.0 zurück, wenn die Equity-Kurve leer ist.
    """

    if not equity_curve:
        return 0.0

    final_value = equity_curve[-1].total_value
    return (final_value - initial_capital) / initial_capital * 100


def max_drawdown_percent(equity_curve: list[EquityPoint]) -> float:
    """Berechnet den maximalen Drawdown der Equity-Kurve in Prozent.

    Der Drawdown misst den grössten Rückgang gegenüber dem bisherigen
    Höchststand der Kurve. Gibt 0.0 zurück, wenn die Equity-Kurve leer ist
    oder es keinen Rückgang gab.
    """

    if not equity_curve:
        return 0.0

    peak = equity_curve[0].total_value
    max_drawdown = 0.0

    for point in equity_curve:
        peak = max(peak, point.total_value)
        drawdown = (peak - point.total_value) / peak * 100
        max_drawdown = max(max_drawdown, drawdown)

    return max_drawdown
