"""Einfache Teststrategie."""

from __future__ import annotations

from tradingbot.data.models import MarketCandle
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal


class SimpleStrategy(Strategy):
    """Einfache Kursvergleichsstrategie."""

    def analyze(
        self,
        candles: list[MarketCandle],
    ) -> TradingSignal:

        if len(candles) < 2:
            return TradingSignal(
                symbol="UNKNOWN",
                signal="HOLD",
                confidence=0.0,
            )

        previous = candles[-2]
        current = candles[-1]

        if current.close > previous.close:
            return TradingSignal(
                symbol=current.symbol,
                signal="BUY",
                confidence=0.5,
            )

        if current.close < previous.close:
            return TradingSignal(
                symbol=current.symbol,
                signal="SELL",
                confidence=0.5,
            )

        return TradingSignal(
            symbol=current.symbol,
            signal="HOLD",
            confidence=0.5,
        )
