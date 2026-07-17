"""Simulierte Marktdaten-Quelle ohne Netzwerkzugriff."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from tradingbot.data.models import MarketCandle
from tradingbot.data.provider import DataProvider

_TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class SimulatedDataProvider(DataProvider):
    """Erzeugt reproduzierbare Kerzen über einen einfachen Zufalls-Walk.

    Platzhalter für eine echte Börsen-Anbindung (siehe
    `tradingbot.data.provider.DataProvider`). Kein Netzwerkzugriff, keine
    echten Marktdaten, kein Live-Trading. Für dasselbe Symbol liefert dieselbe
    Instanz bei gleichem `seed` immer denselben Kursverlauf.
    """

    def __init__(
        self,
        start_price: float = 100.0,
        volatility: float = 0.01,
        seed: int = 42,
    ) -> None:
        self._start_price = start_price
        self._volatility = volatility
        self._seed = seed

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[MarketCandle]:
        """Erzeugt `limit` deterministische Kerzen für `symbol`."""

        if timeframe not in _TIMEFRAME_MINUTES:
            raise ValueError(f"Unbekannter Zeitrahmen: {timeframe}")

        # Eigener Zufallsgenerator je Aufruf, aus Provider-Seed + Symbol
        # abgeleitet: reproduzierbar pro Symbol, aber unterschiedliche
        # Symbole erzeugen unterschiedliche Kursverläufe.
        rng = random.Random(f"{self._seed}:{symbol}")  # noqa: S311 - simulierte Kursdaten, kein Sicherheitskontext

        step = timedelta(minutes=_TIMEFRAME_MINUTES[timeframe])
        now = datetime.now(UTC)

        candles: list[MarketCandle] = []
        price = self._start_price

        for i in range(limit):
            change = rng.uniform(-self._volatility, self._volatility)
            open_price = price
            close_price = max(open_price * (1 + change), 0.01)
            high_price = max(open_price, close_price) * (
                1 + rng.uniform(0, self._volatility)
            )
            low_price = min(open_price, close_price) * (
                1 - rng.uniform(0, self._volatility)
            )
            volume = rng.uniform(100, 1000)

            candles.append(
                MarketCandle(
                    symbol=symbol,
                    timestamp=now - step * (limit - 1 - i),
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                )
            )

            price = close_price

        return candles
