"""Live Broker: strukturelle Vorbereitung für eine echte Exchange-Anbindung.

Kein Netzwerkzugriff, keine HTTP-Bibliothek, keine echte Order-Ausführung -
es wurde noch keine konkrete Börse gewählt. `execute()`/`get_order_status()`
werfen deshalb bewusst `NotImplementedError`. Was bereits real funktioniert:
Credential-Handling (als Konstruktorparameter, siehe unten) und
Rate-Limiting (siehe `_throttle()`) - beide Male reine `Broker`-interne
Implementierungsdetails, weder Teil der `Broker`-ABC (siehe
`execution/broker.py`) noch des `OrderManager`/`Scheduler`.

Credentials werden hier bewusst NICHT aus Umgebungsvariablen gelesen -
das bleibt Aufgabe von `cli/composition.py` (dem einzigen Ort, an dem
konkrete Deployment-Details wie Secrets aufgelöst werden). `LiveBroker`
nimmt sie als fertige Werte entgegen und bleibt dadurch unabhängig vom
Deployment-Kontext testbar.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from tradingbot.execution.broker import Broker
from tradingbot.execution.models import ExecutionResult, Order


class LiveBroker(Broker):
    """Strukturell vollständige `Broker`-Implementierung ohne Exchange-
    Anbindung.

    `min_request_interval_seconds` erzwingt einen Mindestabstand zwischen
    aufeinanderfolgenden Broker-Aufrufen (`execute()` und
    `get_order_status()` gemeinsam gezählt) - eine einfache, lokale
    Drossel, kein Zusammenspiel mit `Scheduler` (bleibt reine
    Zeitsteuerung) oder `OrderManager` (bleibt Lifecycle/Duplicate
    Detection) nötig.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        min_request_interval_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._min_request_interval_seconds = min_request_interval_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        """Wartet, falls nötig, bis seit dem letzten Aufruf mindestens
        `min_request_interval_seconds` vergangen sind."""

        now = self._monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            remaining = self._min_request_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_at = now

    def execute(self, order: Order) -> ExecutionResult:
        """Würde die Order an eine echte Börse senden - noch nicht
        implementiert (keine Börse gewählt, siehe Klassendocstring)."""

        self._throttle()
        raise NotImplementedError(
            "LiveBroker.execute() ist noch nicht implementiert - es wurde noch keine "
            "Exchange-Anbindung gebaut (kein Exchange gewählt, keine HTTP-Bibliothek "
            "eingebunden). Diese Phase bereitet nur Struktur, Credentials und "
            "Rate-Limiting vor."
        )

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        """Würde den Order-Status bei einer echten Börse abfragen - noch
        nicht implementiert (siehe `execute()`)."""

        self._throttle()
        raise NotImplementedError(
            "LiveBroker.get_order_status() ist noch nicht implementiert - es wurde "
            "noch keine Exchange-Anbindung gebaut (siehe LiveBroker.execute())."
        )
