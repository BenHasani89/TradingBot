"""Ziel-Allokations-Policies: einfache, zustandslose Varianten.

Bewusst backtest-/live-unabhängig konzipiert (wie `Strategy.analyze()`) -
keine dieser Klassen weiss, ob sie in einem Backtest oder live aufgerufen
wird. `portfolio_status` ist optional und wird von den hier implementierten
einfachen Policies nicht benötigt, steht aber für spätere Policies bereit,
die aktuelle Bestände kennen müssen (z. B. Turnover-Minimierung).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradingbot.data.models import MarketCandle
from tradingbot.portfolio.models import PortfolioStatus


class TargetAllocationPolicy(ABC):
    """Abstrakte Basis: liefert Ziel-Gewichte je Symbol (Summe ≤ 1.0,
    fehlendes Restkapital bleibt Cash)."""

    @abstractmethod
    def target_weights(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        portfolio_status: PortfolioStatus | None = None,
    ) -> dict[str, float]:
        """Berechnet die Ziel-Gewichte für die übergebenen Symbole."""
        ...


class EqualWeightPolicy(TargetAllocationPolicy):
    """Gleichgewichtung über alle übergebenen Symbole (1/n je Symbol)."""

    def target_weights(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        portfolio_status: PortfolioStatus | None = None,
    ) -> dict[str, float]:
        symbols = list(candles_by_symbol.keys())
        if not symbols:
            return {}

        weight = 1.0 / len(symbols)
        return {symbol: weight for symbol in symbols}


class FixedTargetPolicy(TargetAllocationPolicy):
    """Feste, vom Nutzer vorgegebene Ziel-Gewichte - unabhängig von
    Kursdaten oder Portfolio-Zustand."""

    def __init__(self, weights: dict[str, float]) -> None:
        self._weights = weights

    def target_weights(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        portfolio_status: PortfolioStatus | None = None,
    ) -> dict[str, float]:
        return dict(self._weights)
