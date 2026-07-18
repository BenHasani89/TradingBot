"""Marktdaten-Verwaltung."""

from __future__ import annotations

from datetime import datetime

from tradingbot.data.models import MarketCandle


class MarketDataStore:
    """Speichert und liefert Marktdaten.

    Idempotent gegenüber Symbol+Zeitstempel: eine bereits bekannte Kerze
    wird nicht erneut gespeichert. Das verhindert unbegrenztes Wachstum bei
    wiederholten Abrufen überlappender Fenster im Dauerbetrieb. Kennt
    bewusst keinen Session-/Zyklus-Zustand - das bleibt Aufgabe der
    aufrufenden Schicht (siehe `paper_trading.engine.PaperTradingEngine`).
    """

    def __init__(self) -> None:
        self._candles: list[MarketCandle] = []
        self._known_keys: set[tuple[str, datetime]] = set()

    def add(self, candle: MarketCandle) -> bool:
        """Fügt eine Kurskerze hinzu, falls sie noch nicht bekannt ist.

        Gibt zurück, ob die Kerze tatsächlich neu war (`False`, wenn bereits
        eine Kerze mit demselben Symbol und Zeitstempel gespeichert ist).
        """

        key = (candle.symbol, candle.timestamp)
        if key in self._known_keys:
            return False

        self._known_keys.add(key)
        self._candles.append(candle)
        return True

    def add_many(self, candles: list[MarketCandle]) -> list[MarketCandle]:
        """Fügt mehrere Kerzen hinzu, gibt die tatsächlich neuen zurück
        (in der übergebenen Reihenfolge)."""

        return [candle for candle in candles if self.add(candle)]

    def all(self) -> list[MarketCandle]:
        """Gibt alle gespeicherten Kerzen zurück."""
        return self._candles

    def latest(self, symbol: str, limit: int) -> list[MarketCandle]:
        """Gibt die letzten `limit` Kerzen für `symbol` zurück (chronologisch)."""
        matching = [candle for candle in self._candles if candle.symbol == symbol]
        return matching[-limit:]
