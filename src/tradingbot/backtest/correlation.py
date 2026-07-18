"""Asset-Korrelationen: Markt- und Strategie-Korrelation über mehrere Assets.

Reine Auswertung bereits vorhandener Preis-/Equity-Daten (keine neue
Simulationslogik). Nutzt `statistics.correlation()` (Python 3.10+) aus der
Standardbibliothek - keine externen Bibliotheken.
"""

from __future__ import annotations

import statistics

from tradingbot.backtest.models import EquityPoint
from tradingbot.data.models import MarketCandle


def _correlation_matrix(series_by_symbol: dict[str, list[float]]) -> dict[tuple[str, str], float]:
    """Pearson-Korrelation zwischen allen Paaren von Wertreihen.

    Reihen werden auf die gemeinsame Länge gekürzt. Paare mit weniger als
    zwei gemeinsamen Werten oder ohne Streuung (konstante Reihe) werden
    ausgelassen, statt eine Ausnahme auszulösen.
    """

    symbols = list(series_by_symbol.keys())
    result: dict[tuple[str, str], float] = {}

    for i, symbol_a in enumerate(symbols):
        for symbol_b in symbols[i + 1 :]:
            values_a = series_by_symbol[symbol_a]
            values_b = series_by_symbol[symbol_b]
            length = min(len(values_a), len(values_b))
            if length < 2:
                continue

            values_a = values_a[:length]
            values_b = values_b[:length]
            if len(set(values_a)) < 2 or len(set(values_b)) < 2:
                continue  # konstante Reihe -> Korrelation nicht definiert

            result[(symbol_a, symbol_b)] = statistics.correlation(values_a, values_b)

    return result


def _price_returns(candles: list[MarketCandle]) -> list[float]:
    """Perioden-Renditen der Schlusskurse."""

    closes = [candle.close for candle in candles]
    return [
        (current - previous) / previous
        for previous, current in zip(closes, closes[1:], strict=False)
    ]


def market_correlation(
    candles_by_symbol: dict[str, list[MarketCandle]],
) -> dict[tuple[str, str], float]:
    """Korrelation der Kursrenditen zwischen Assets - reine Marktbetrachtung,
    unabhängig von einer Strategie.
    """

    returns_by_symbol = {
        symbol: _price_returns(candles) for symbol, candles in candles_by_symbol.items()
    }
    return _correlation_matrix(returns_by_symbol)


def strategy_correlation(
    equity_curve_by_symbol: dict[str, list[EquityPoint]],
) -> dict[tuple[str, str], float]:
    """Korrelation der Sub-Portfolio-Equity-Verläufe je Asset
    (`equity_curve_by_symbol`, siehe `portfolio_engine.py`).

    Misst **nicht** die Korrelation von Asset-Renditen (dafür siehe
    `market_correlation`), sondern die Korrelation der notionalen
    Kapitalstände je Asset - also Cash-Anteil plus aktueller Positionswert,
    inklusive der Zeiträume, in denen ein Asset gar keine offene Position
    hält (dort ist der Kapitalstand reines, unverändertes Cash). Zwei
    Assets, die beide meist nur Cash halten und selten handeln, können
    dadurch hohe, aber wenig aussagekräftige Korrelationswerte zeigen -
    die Kennzahl misst dann eher "bewegt sich das Kapitalengagement
    gemeinsam" als "bewegen sich Kursbewegungen gemeinsam".

    Nutzt bewusst Wertniveaus statt Renditen: Der Kapitalstand eines Assets
    ist `0.0`, solange keine Position offen ist - eine Rendite (Division
    durch den Vorwert) wäre dort nicht definiert, und selbst wenn, hätte ein
    Sprung von/zu `0.0` keine ökonomische Bedeutung (kein Kursgewinn,
    sondern der Moment des Investierens/Deinvestierens).
    """

    values_by_symbol = {
        symbol: [point.total_value for point in curve]
        for symbol, curve in equity_curve_by_symbol.items()
    }
    return _correlation_matrix(values_by_symbol)
