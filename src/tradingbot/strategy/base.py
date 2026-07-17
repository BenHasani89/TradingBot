"""Basis-Klasse für Trading-Strategien."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradingbot.data.models import MarketCandle
from tradingbot.strategy.models import TradingSignal


class Strategy(ABC):
    """Abstrakte Basis einer Strategie."""

    @abstractmethod
    def analyze(
        self,
        candles: list[MarketCandle],
    ) -> TradingSignal:
        """Analysiert Marktdaten und erzeugt ein Signal."""
        pass
