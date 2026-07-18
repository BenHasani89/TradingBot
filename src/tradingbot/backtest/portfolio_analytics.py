"""Portfolio-Risikoanalyse: Beitrag je Asset zu Rendite und Drawdown,
Exposure, Risiko je Asset und Konzentrationsrisiko.

Reine Auswertung eines bereits abgeschlossenen `PortfolioBacktestResult` -
keine neue Simulationslogik, keine Trading- oder Kapitalentscheidungen.
"""

from __future__ import annotations

from tradingbot.backtest.metrics import (
    max_drawdown_percent,
    sharpe_ratio,
    volatility_percent,
)
from tradingbot.backtest.models import EquityPoint
from tradingbot.backtest.portfolio_engine import PortfolioBacktestResult


def asset_contribution_to_return(result: PortfolioBacktestResult) -> dict[str, float]:
    """Rendite-Beitrag je Asset: Endwert des Assets minus dessen
    ursprünglich zugeteiltes Kapital (`allocation`).

    Realisierte und unrealisierte Gewinne/Verluste sind darin automatisch
    beide enthalten, da `equity_curve_by_symbol` bereits beides abbildet
    (siehe `portfolio_engine.py`) - keine separate Addition von
    `ClosedTrade`-Werten, um Doppelzählung zu vermeiden.
    """

    contributions: dict[str, float] = {}

    for symbol, curve in result.equity_curve_by_symbol.items():
        final_value = curve[-1].total_value if curve else result.allocation.get(symbol, 0.0)
        contributions[symbol] = final_value - result.allocation.get(symbol, 0.0)

    return contributions


def _find_drawdown_window(equity_curve: list[EquityPoint]) -> tuple[int | None, int | None]:
    """Findet die Indizes von Hoch- und Tiefpunkt des maximalen Drawdowns.

    Gleiche Logik wie `metrics.max_drawdown_percent()`, gibt zusätzlich die
    Positionen zurück statt nur den Prozentwert. Gibt `(None, None)`
    zurück, wenn die Kurve leer ist oder nie unter ihr bisheriges Hoch
    gefallen ist (kein Drawdown).
    """

    if not equity_curve:
        return None, None

    peak_index = 0
    peak_value = equity_curve[0].total_value
    max_drawdown = 0.0
    drawdown_peak_index: int | None = None
    drawdown_trough_index: int | None = None

    for index, point in enumerate(equity_curve):
        if point.total_value > peak_value:
            peak_value = point.total_value
            peak_index = index

        drawdown = peak_value - point.total_value
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            drawdown_peak_index = peak_index
            drawdown_trough_index = index

    return drawdown_peak_index, drawdown_trough_index


def asset_contribution_to_drawdown(result: PortfolioBacktestResult) -> dict[str, float]:
    """Beitrag jedes Assets zum maximalen Portfolio-Drawdown, als Anteil
    (Prozent) des gesamten Drawdown-**Betrags** - nicht als absolute
    Wertänderung. Die Beiträge summieren sich näherungsweise auf 100 %,
    können aber auch negativ sein (ein Asset, das im Drawdown-Fenster des
    Portfolios selbst zulegte, wirkte dem Drawdown entgegen).

    Gibt für jedes Asset `0.0` zurück, wenn kein Portfolio-Drawdown
    aufgetreten ist.
    """

    peak_index, trough_index = _find_drawdown_window(result.equity_curve)
    symbols = list(result.equity_curve_by_symbol.keys())

    if peak_index is None or trough_index is None:
        return {symbol: 0.0 for symbol in symbols}

    portfolio_drawdown_amount = (
        result.equity_curve[peak_index].total_value - result.equity_curve[trough_index].total_value
    )
    if portfolio_drawdown_amount == 0.0:
        return {symbol: 0.0 for symbol in symbols}

    contributions: dict[str, float] = {}
    for symbol in symbols:
        curve = result.equity_curve_by_symbol[symbol]
        asset_change = curve[peak_index].total_value - curve[trough_index].total_value
        contributions[symbol] = asset_change / portfolio_drawdown_amount * 100

    return contributions


def exposure_over_time(result: PortfolioBacktestResult) -> dict[str, list[float]]:
    """Anteil jedes Assets am Portfolio-Gesamtwert, als Zeitreihe.

    Basiert auf `equity_curve_by_symbol` (notionales Sub-Portfolio je
    Asset, siehe `portfolio_engine.py`) - spiegelt also den Anteil am
    zugeteilten Kapital wider (inkl. nicht investiertem Cash-Anteil),
    nicht nur reine Positions-Marktrisiko-Exposure.

    Zeitschritte mit Portfolio-Gesamtwert `0` ergeben `0.0` statt einer
    Division-durch-Null-Ausnahme.
    """

    symbols = list(result.equity_curve_by_symbol.keys())
    exposure: dict[str, list[float]] = {symbol: [] for symbol in symbols}

    for t, portfolio_point in enumerate(result.equity_curve):
        total = portfolio_point.total_value
        for symbol in symbols:
            asset_value = result.equity_curve_by_symbol[symbol][t].total_value
            exposure[symbol].append(asset_value / total if total != 0 else 0.0)

    return exposure


def risk_per_asset(
    result: PortfolioBacktestResult,
    periods_per_year: int,
) -> dict[str, dict[str, float]]:
    """Volatilität, Sharpe Ratio und Max Drawdown je Asset.

    Direkte Wiederverwendung der bestehenden `metrics.py`-Funktionen auf
    `equity_curve_by_symbol[symbol]` - strukturell identisch zu einer
    normalen Equity-Kurve, keine neue Kennzahlen-Logik nötig.
    """

    return {
        symbol: {
            "volatility_percent": volatility_percent(curve, periods_per_year),
            "sharpe_ratio": sharpe_ratio(curve, periods_per_year),
            "max_drawdown_percent": max_drawdown_percent(curve),
        }
        for symbol, curve in result.equity_curve_by_symbol.items()
    }


def concentration_risk_over_time(result: PortfolioBacktestResult) -> list[float]:
    """Herfindahl-Hirschman-Index der Asset-Gewichtungen je Zeitschritt.

    Werte reichen von `1/n` (bei n Assets perfekt gleichverteilt) bis `1.0`
    (vollständig in einem Asset konzentriert). Gibt eine leere Liste
    zurück, wenn keine Assets vorhanden sind.
    """

    exposure = exposure_over_time(result)
    symbols = list(exposure.keys())
    if not symbols:
        return []

    step_count = len(result.equity_curve)
    return [sum(exposure[symbol][t] ** 2 for symbol in symbols) for t in range(step_count)]
