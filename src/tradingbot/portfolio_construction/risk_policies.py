"""Risiko-basierte Ziel-Allokations-Policies: vereinfachtes Risk Parity und
Volatility Targeting.

Bewusst vereinfacht: inverse Volatilitätsgewichtung statt einer vollen
Kovarianzmatrix-Optimierung (würde einen numerischen Solver benötigen -
keine externen Bibliotheken erlaubt). Nur Abwärts-Skalierung bei Volatility
Targeting (kein Hebel, das System kennt kein Margin).
"""

from __future__ import annotations

import math
import statistics

from tradingbot.data.models import MarketCandle
from tradingbot.portfolio.models import PortfolioStatus
from tradingbot.portfolio_construction.target_allocation import TargetAllocationPolicy


def _price_returns(candles: list[MarketCandle]) -> list[float]:
    """Perioden-Renditen der Schlusskurse."""

    closes = [candle.close for candle in candles]
    return [
        (current - previous) / previous
        for previous, current in zip(closes, closes[1:], strict=False)
    ]


def _price_volatility(candles: list[MarketCandle], periods_per_year: int) -> float:
    """Annualisierte Standardabweichung der Kursrenditen. `0.0`, wenn
    weniger als zwei Renditen vorliegen (zu wenig Daten)."""

    returns = _price_returns(candles)
    if len(returns) < 2:
        return 0.0

    return statistics.stdev(returns) * math.sqrt(periods_per_year)


class RiskParityPolicy(TargetAllocationPolicy):
    """Gewichtung invers proportional zur historischen Volatilität je Asset
    (vereinfachtes Risk Parity, ohne Korrelationen/Kovarianzmatrix).

    Fällt auf Gleichgewichtung zurück, wenn für kein Asset eine Volatilität
    messbar ist (z. B. zu wenig historische Daten).
    """

    def __init__(self, lookback: int, periods_per_year: dict[str, int]) -> None:
        self._lookback = lookback
        self._periods_per_year = periods_per_year

    def target_weights(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        portfolio_status: PortfolioStatus | None = None,
    ) -> dict[str, float]:
        symbols = list(candles_by_symbol.keys())
        if not symbols:
            return {}

        volatilities = {
            symbol: _price_volatility(
                candles_by_symbol[symbol][-self._lookback :],
                self._periods_per_year[symbol],
            )
            for symbol in symbols
        }
        inverse_volatilities = {
            symbol: (1.0 / vol if vol > 0 else 0.0) for symbol, vol in volatilities.items()
        }

        total = sum(inverse_volatilities.values())
        if total == 0.0:
            weight = 1.0 / len(symbols)
            return {symbol: weight for symbol in symbols}

        return {symbol: value / total for symbol, value in inverse_volatilities.items()}


class VolatilityTargetPolicy(TargetAllocationPolicy):
    """Skaliert die Gewichte einer Basis-Policy gemeinsam nach unten, wenn
    die geschätzte Portfolio-Volatilität über dem Zielwert liegt.

    Schätzt die Portfolio-Volatilität vereinfachend als gewichtete Summe der
    Einzel-Volatilitäten (ohne Korrelationen, konsistent mit
    `RiskParityPolicy`). Nur Abwärts-Skalierung - nicht erreichte Zielwerte
    werden nicht durch Hebel ausgeglichen, das ungenutzte Restkapital bleibt
    Cash.
    """

    def __init__(
        self,
        base_policy: TargetAllocationPolicy,
        target_volatility_percent: float,
        lookback: int,
        periods_per_year: dict[str, int],
    ) -> None:
        self._base_policy = base_policy
        self._target_volatility_percent = target_volatility_percent
        self._lookback = lookback
        self._periods_per_year = periods_per_year

    def target_weights(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        portfolio_status: PortfolioStatus | None = None,
    ) -> dict[str, float]:
        base_weights = self._base_policy.target_weights(candles_by_symbol, portfolio_status)
        if not base_weights:
            return base_weights

        estimated_volatility_percent = sum(
            base_weights.get(symbol, 0.0)
            * _price_volatility(
                candles_by_symbol[symbol][-self._lookback :],
                self._periods_per_year[symbol],
            )
            for symbol in candles_by_symbol
        ) * 100

        if estimated_volatility_percent <= self._target_volatility_percent:
            # Kein Skalierungsbedarf - deckt auch den Fall estimated == 0.0 ab.
            return base_weights

        scale = self._target_volatility_percent / estimated_volatility_percent
        return {symbol: weight * scale for symbol, weight in base_weights.items()}
