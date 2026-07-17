"""Abstrakte Schnittstelle für Marktdaten-Quellen."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradingbot.data.models import MarketCandle


class DataProvider(ABC):
    """Abstrakte Basis einer Marktdaten-Quelle.

    Implementierungen liefern Kerzendaten für ein Symbol und einen
    Zeitrahmen - unabhängig davon, ob die Daten simuliert sind oder später
    von einer echten Börsen-API stammen (siehe `SimulatedDataProvider` als
    aktuell einzige Implementierung).
    """

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[MarketCandle]:
        """Liefert die letzten `limit` Kerzen für `symbol` im `timeframe`."""
        ...
