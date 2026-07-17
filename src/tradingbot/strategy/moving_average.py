"""Gleitender-Durchschnitt-Kreuzungsstrategie (Moving Average Crossover)."""

from __future__ import annotations

from tradingbot.data.models import MarketCandle
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal


class MovingAverageCrossoverStrategy(Strategy):
    """Vergleicht einen kurzen und einen langen einfachen gleitenden
    Durchschnitt (SMA).

    BUY, wenn der kurze SMA über dem langen liegt; SELL, wenn er darunter
    liegt; HOLD, wenn nicht genug Kerzen für den langen SMA vorliegen oder
    beide SMA identisch sind. Die Konfidenz wird aus der relativen Differenz
    der beiden SMA abgeleitet und auf `[0.0, 1.0]` begrenzt.
    """

    def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
        self._short_window = short_window
        self._long_window = long_window

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        if len(candles) < self._long_window:
            symbol = candles[-1].symbol if candles else "UNKNOWN"
            return TradingSignal(symbol=symbol, signal="HOLD", confidence=0.0)

        symbol = candles[-1].symbol

        short_sma = _simple_moving_average(candles, self._short_window)
        long_sma = _simple_moving_average(candles, self._long_window)

        if short_sma == long_sma:
            return TradingSignal(symbol=symbol, signal="HOLD", confidence=0.0)

        confidence = min(abs(short_sma - long_sma) / long_sma, 1.0)

        if short_sma > long_sma:
            return TradingSignal(symbol=symbol, signal="BUY", confidence=confidence)

        return TradingSignal(symbol=symbol, signal="SELL", confidence=confidence)


def _simple_moving_average(candles: list[MarketCandle], window: int) -> float:
    """Berechnet den einfachen gleitenden Durchschnitt (SMA) der letzten
    `window` Schlusskurse.
    """

    recent = candles[-window:]
    return sum(candle.close for candle in recent) / window
