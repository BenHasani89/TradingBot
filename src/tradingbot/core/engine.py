"""Trading-Kern: Ablaufsteuerung und Zustandsverwaltung."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, TypedDict

from loguru import logger

from tradingbot.config.settings import MODE

Modus = Literal["paper_trading"]


class EngineStatus(TypedDict):
    running: bool
    started_at: datetime | None
    mode: Modus


class TradingEngine:
    """Zentrale Ablaufsteuerung des Trading-Bots."""

    def __init__(self) -> None:
        self._running = False
        self._started_at: datetime | None = None
        self._mode: Modus = MODE

    def start(self) -> None:
        """Startet die Engine."""

        self._running = True
        self._started_at = datetime.now(UTC)

        logger.info(
            "Trading-Engine gestartet (Modus: {})",
            self._mode,
        )

    def stop(self) -> None:
        """Stoppt die Engine."""

        self._running = False

        logger.info("Trading-Engine gestoppt")

    def status(self) -> EngineStatus:
        """Gibt den aktuellen Status zurück."""

        return {
            "running": self._running,
            "started_at": self._started_at,
            "mode": self._mode,
        }
