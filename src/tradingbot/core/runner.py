"""Verbindet DataProvider, MarketDataStore und TradingOrchestrator zu einem
einzelnen Paper-Trading-Durchlauf.
"""

from __future__ import annotations

from loguru import logger

from tradingbot.core.engine import TradingEngine
from tradingbot.core.models import TradingCycleResult
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.market import MarketDataStore
from tradingbot.data.provider import DataProvider


class TradingBotRunner:
    """Führt einen einzelnen Ablauf von Datenbeschaffung bis Trading-Zyklus aus.

    Holt Kerzen vom `DataProvider`, legt sie im `MarketDataStore` ab, liest
    die benötigten Kerzen wieder daraus und übergibt sie an den
    `TradingOrchestrator`. Enthält bewusst keine Schleife und keinen
    Scheduler - das bleibt ein späterer, eigener Baustein.
    """

    def __init__(
        self,
        engine: TradingEngine,
        provider: DataProvider,
        store: MarketDataStore,
        orchestrator: TradingOrchestrator,
        symbol: str,
        timeframe: str,
        candle_limit: int,
    ) -> None:
        self._engine = engine
        self._provider = provider
        self._store = store
        self._orchestrator = orchestrator
        self._symbol = symbol
        self._timeframe = timeframe
        self._candle_limit = candle_limit

    def run_once(self) -> TradingCycleResult:
        """Führt einen vollständigen Durchlauf aus und gibt das Ergebnis zurück.

        Ablauf: Der `DataProvider` liefert Kerzen -> jede Kerze wird im
        `MarketDataStore` gespeichert -> die benötigten Kerzen werden über
        `MarketDataStore.latest()` wieder gelesen -> Übergabe an
        `TradingOrchestrator.run_cycle()`.

        Fehler (z. B. inaktive Engine, unbekannter Zeitrahmen) werden nicht
        abgefangen, sondern laufen bewusst durch, statt sie still zu
        verschlucken.
        """

        candles = self._provider.get_candles(
            symbol=self._symbol,
            timeframe=self._timeframe,
            limit=self._candle_limit,
        )

        for candle in candles:
            self._store.add(candle)

        recent_candles = self._store.latest(self._symbol, self._candle_limit)

        logger.info(
            "Runner-Zyklus für {} ({} Kerzen)",
            self._symbol,
            len(recent_candles),
        )

        return self._orchestrator.run_cycle(recent_candles)
