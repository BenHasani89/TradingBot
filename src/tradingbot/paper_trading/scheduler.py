"""Zeitsteuerung für wiederholte Trading-Zyklen.

Reine Timing-Mechanik - kennt keine Trading-Logik, keinen Zustand, keine
Persistenz. `Scheduler` ist bewusst schmal gehalten, damit ein späterer
Wechsel zu APScheduler (bereits als Dependency vorbereitet, aktuell nicht
eingebunden) ausschliesslich diese Datei betrifft.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable


class Scheduler(ABC):
    """Abstrakte Zeitsteuerung: ruft eine Callback-Funktion wiederholt auf."""

    @abstractmethod
    def run(self, callback: Callable[[], None], interval_seconds: float) -> None:
        """Ruft `callback` wiederholt im Abstand von `interval_seconds`
        Sekunden auf, bis `stop()` aufgerufen wird."""

    @abstractmethod
    def stop(self) -> None:
        """Beendet die laufende Schleife nach dem aktuellen Zyklus."""


class SimpleLoopScheduler(Scheduler):
    """Stdlib-only Zeitsteuerung über eine einfache `while`-Schleife.

    Kein Cron, keine Job-Persistenz, keine parallelen Jobs - bewusst
    minimal für diese Phase. `sleep` ist injizierbar, damit Tests ohne
    reale Wartezeit auskommen.
    """

    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self._sleep = sleep
        self._running = False

    def run(self, callback: Callable[[], None], interval_seconds: float) -> None:
        """Startet die Schleife. Blockiert, bis `stop()` aufgerufen wird
        (typischerweise aus `callback` selbst heraus)."""

        self._running = True
        while self._running:
            callback()
            if self._running:
                self._sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False
