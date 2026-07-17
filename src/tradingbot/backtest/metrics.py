"""Reine Berechnungsfunktionen für Backtest-Kennzahlen (keine Klassen)."""

from __future__ import annotations

import math
import statistics

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


def _period_returns(equity_curve: list[EquityPoint]) -> list[float]:
    """Perioden-Renditen zwischen aufeinanderfolgenden Punkten der Equity-Kurve."""

    return [
        (current.total_value - previous.total_value) / previous.total_value
        for previous, current in zip(equity_curve, equity_curve[1:], strict=False)
    ]


def volatility_percent(
    equity_curve: list[EquityPoint],
    periods_per_year: int,
) -> float:
    """Annualisierte Standardabweichung der Perioden-Renditen, in Prozent.

    `periods_per_year` muss explizit angegeben werden (z. B. 8760 für
    Stundenkerzen bei einem 24/7-Markt, 252 für Tageskerzen bei Aktien) -
    wird bewusst nicht aus den Zeitstempeln der Equity-Kurve abgeleitet.

    Gibt 0.0 zurück, wenn weniger als zwei Perioden-Renditen vorliegen.
    """

    returns = _period_returns(equity_curve)
    if len(returns) < 2:
        return 0.0

    return statistics.stdev(returns) * math.sqrt(periods_per_year) * 100


def sharpe_ratio(
    equity_curve: list[EquityPoint],
    periods_per_year: int,
    risk_free_rate: float = 0.0,
) -> float:
    """Annualisierte Sharpe Ratio der Equity-Kurve.

    `risk_free_rate` ist die risikofreie Rendite pro Jahr (Standard `0.0`).
    `periods_per_year` hat dieselbe Bedeutung wie bei `volatility_percent`.

    Gibt 0.0 zurück, wenn weniger als zwei Perioden-Renditen vorliegen oder
    die Volatilität 0 ist (keine Schwankung, keine sinnvolle Ratio).
    """

    returns = _period_returns(equity_curve)
    if len(returns) < 2:
        return 0.0

    std_return = statistics.stdev(returns)
    if math.isclose(std_return, 0.0, abs_tol=1e-12):
        return 0.0

    mean_return = statistics.mean(returns)
    risk_free_rate_per_period = risk_free_rate / periods_per_year

    return (mean_return - risk_free_rate_per_period) / std_return * math.sqrt(periods_per_year)


def annualized_return_percent(
    equity_curve: list[EquityPoint],
    initial_capital: float,
    periods_per_year: int,
) -> float:
    """Rechnet die Gesamtrendite der Equity-Kurve per Zinseszins auf eine
    jährliche Rate hoch.

    Die Anzahl vergangener Jahre wird als `len(equity_curve) / periods_per_year`
    angenähert. `periods_per_year` hat dieselbe Bedeutung wie bei
    `volatility_percent`. Gibt 0.0 zurück, wenn die Equity-Kurve leer ist.
    """

    if not equity_curve:
        return 0.0

    total_return = performance_percent(initial_capital, equity_curve) / 100
    years = len(equity_curve) / periods_per_year

    if years <= 0:
        return 0.0

    return ((1 + total_return) ** (1 / years) - 1) * 100


def calmar_ratio(
    equity_curve: list[EquityPoint],
    initial_capital: float,
    periods_per_year: int,
) -> float:
    """Verhältnis von annualisierter Rendite zu maximalem Drawdown
    (jeweils in Prozent-Punkten).

    Gibt `float('inf')` zurück, wenn kein Drawdown aufgetreten ist, aber
    eine positive annualisierte Rendite erzielt wurde, und `0.0`, wenn weder
    Rendite noch Drawdown vorliegen.
    """

    annualized_return = annualized_return_percent(equity_curve, initial_capital, periods_per_year)
    drawdown = max_drawdown_percent(equity_curve)

    if drawdown == 0.0:
        return float("inf") if annualized_return > 0.0 else 0.0

    return annualized_return / drawdown
