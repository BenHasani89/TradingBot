"""Buy-and-Hold-Baseline-Strategie."""

from __future__ import annotations

from tradingbot.data.models import MarketCandle
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal


class BuyAndHoldStrategy(Strategy):
    """Kauft bei der ersten gültigen Analyse einmalig und hält danach nur
    noch - dient als Vergleichsmassstab (Baseline) für aktive Strategien.
    Verkauft nie.
    """

    def __init__(self, symbol: str) -> None:
        self._symbol = symbol
        self._has_bought = False

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        if not candles:
            return TradingSignal(symbol=self._symbol, signal="HOLD", confidence=0.0)

        if not self._has_bought:
            self._has_bought = True
            return TradingSignal(symbol=self._symbol, signal="BUY", confidence=1.0)

        return TradingSignal(symbol=self._symbol, signal="HOLD", confidence=0.0)
