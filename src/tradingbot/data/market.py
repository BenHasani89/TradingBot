"""Marktdaten-Verwaltung."""

from __future__ import annotations

from tradingbot.data.models import MarketCandle


class MarketDataStore:
    """Speichert und liefert Marktdaten."""

    def __init__(self) -> None:
        self._candles: list[MarketCandle] = []

    def add(self, candle: MarketCandle) -> None:
        """Fügt eine Kurskerze hinzu."""
        self._candles.append(candle)

    def all(self) -> list[MarketCandle]:
        """Gibt alle gespeicherten Kerzen zurück."""
        return self._candles
