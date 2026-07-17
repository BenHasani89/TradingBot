"""Trading-Kern: Ablaufsteuerung und Zustandsverwaltung des Bots.

Enthaelt bewusst keine Boersen-Anbindung und loest keine Trades aus - das ist
Aufgabe spaeterer Module (Ausfuehrungssystem, Strategie-System). Diese
Komponente kennt nur den Aktiv-Status des Bots selbst.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, TypedDict

from loguru import logger

Modus = Literal["paper_trading"]


class EngineStatus(TypedDict):
    """Rueckgabetyp von :meth:`TradingEngine.status`."""

    running: bool
    started_at: datetime | None
    mode: Modus


class TradingEngine:
    """Zentrale Ablaufsteuerung des Trading-Bots.

    Verwaltet ausschliesslich, ob der Bot aktiv ist und seit wann. Arbeitet
    aktuell nur im Modus ``paper_trading``.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._started_at: datetime | None = None
        self._mode: Modus = "paper_trading"

    def start(self) -> None:
        """Setzt den Bot auf aktiv und speichert den Startzeitpunkt."""
        self._running = True
        self._started_at = datetime.now(UTC)
        logger.info("Trading-Engine gestartet (Modus: {})", self._mode)

    def stop(self) -> None:
        """Setzt den Bot auf inaktiv."""
        self._running = False
        logger.info("Trading-Engine gestoppt")

    def status(self) -> EngineStatus:
        """Gibt den aktuellen Status der Engine zurueck.

        Returns:
            Dictionary mit den Schluesseln ``running``, ``started_at`` und
            ``mode``.
        """
        return {
            "running": self._running,
            "started_at": self._started_at,
            "mode": self._mode,
        }
