"""Order Reconciliation: vergleicht lokale `OrderRecord`-Zustände mit dem
tatsächlichen Broker-Status.

Reine Betriebsprüfung, kein Bestandteil des Order-Lifecycles selbst - dafür
bleibt `execution.order_manager.OrderManager` ausschliesslich zuständig
(Lifecycle, Duplicate Detection, Broker-Aufruf, lokale Order-Verwaltung).
Läuft im Runtime-Layer (`paper_trading/`), nicht im Execution-Layer, weil
Reconciliation eine periodische, session-bezogene Betriebsprüfung ist,
keine Aufgabe, die `TradingOrchestrator` pro Zyklus ausführt - dadurch
strukturell (nicht nur zufällig) von Backtest/Research getrennt, analog zu
`paper_trading/health.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.execution.broker import Broker
from tradingbot.execution.models import ExecutionStatus, OrderStatus, derive_order_status
from tradingbot.execution.order_repository import OrderRepository

_PENDING_STATUSES = {OrderStatus.CREATED, OrderStatus.SUBMITTED, OrderStatus.UNKNOWN}
"""Status, die noch kein vom Broker direkt bestätigtes Endergebnis tragen -
`FILLED`/`FAILED` kamen bereits als definitive Antwort auf einen
`execute()`-Aufruf zustande und werden von `reconcile_pending()` deshalb
nicht erneut abgefragt (spart Broker-Anfragen, siehe Rate-Limiting in
`execution/live_broker.py`)."""


@dataclass
class ReconciliationResult:
    """Ergebnis eines Reconciliation-Vergleichs für eine einzelne Order.

    `local_status`/`broker_status` sind `None`, wenn die jeweilige Seite
    diese `client_order_id` nicht kennt. `matched=True` bedeutet: der
    lokale Lifecycle-Status entspricht dem, was laut Broker tatsächlich
    passiert ist - `reason` erklärt in jedem Fall (auch bei `matched=True`)
    kurz, warum.
    """

    client_order_id: str
    local_status: OrderStatus | None
    broker_status: ExecutionStatus | None
    matched: bool
    reason: str


class ReconciliationService:
    """Vergleicht lokale `OrderRecord`-Zustände mit dem tatsächlichen
    Broker-Status - erkennt insbesondere bei `SUBMITTED`/`UNKNOWN`
    hängengebliebene Orders, deren wahrer Ausgang lokal nie ankam.

    Verändert weder lokalen noch Broker-seitigen Zustand (reine Prüfung,
    keine Korrektur - keine automatische Portfolio-Korrektur, kein Replay).
    Abhängigkeiten ausschliesslich per Injection - keine direkte SQLite-
    Verbindung, keine Kenntnis von Session-, Portfolio- oder Risk-Konzepten.

    `PaperTradingEngine.start()` ruft `reconcile_pending()` auf und
    reagiert selbst auf das Ergebnis (Kill-Switch, Audit-Event, Start-
    Abbruch bei Mismatch) - diese Klasse liefert nur die Vergleichsdaten,
    die Eskalation bleibt bewusst ausserhalb. Eine laufende (nicht nur
    Start-)Kadenz sowie CLI-Anbindung bleiben einer eigenen, späteren
    Runtime-Phase vorbehalten.
    """

    def __init__(self, broker: Broker, order_repository: OrderRepository) -> None:
        self._broker = broker
        self._order_repository = order_repository

    def reconcile_order(self, client_order_id: str) -> ReconciliationResult:
        """Vergleicht eine einzelne Order.

        Ist die Order lokal unbekannt, wird der Broker gar nicht erst
        gefragt (nichts, das sich lokal zuordnen liesse). Kennt der Broker
        die Order nicht, ist das Ergebnis unabhängig vom lokalen Status ein
        Mismatch. Andernfalls wird der lokale `OrderStatus` gegen den aus
        dem Broker-`ExecutionStatus` erwarteten Status geprüft.
        """

        record = self._order_repository.get(client_order_id)
        if record is None:
            return ReconciliationResult(
                client_order_id=client_order_id,
                local_status=None,
                broker_status=None,
                matched=False,
                reason="Order lokal nicht bekannt (kein OrderRecord vorhanden).",
            )

        broker_result = self._broker.get_order_status(client_order_id)
        if broker_result is None:
            return ReconciliationResult(
                client_order_id=client_order_id,
                local_status=record.status,
                broker_status=None,
                matched=False,
                reason=(
                    f"Broker kennt diese Order nicht (lokaler Status: "
                    f"{record.status.value})."
                ),
            )

        broker_status = broker_result.status
        # Nutzt dieselbe Ableitung wie OrderManager (inkl. filled_quantity,
        # z. B. FILLED vs. PARTIALLY_FILLED) statt einer eigenen, separat
        # gepflegten Zuordnung - garantiert identische Logik auf beiden
        # Seiten (siehe execution.models.derive_order_status()).
        expected_local_status = derive_order_status(broker_result)

        if record.status == expected_local_status:
            return ReconciliationResult(
                client_order_id=client_order_id,
                local_status=record.status,
                broker_status=broker_status,
                matched=True,
                reason="Lokaler Status stimmt mit dem Broker überein.",
            )

        return ReconciliationResult(
            client_order_id=client_order_id,
            local_status=record.status,
            broker_status=broker_status,
            matched=False,
            reason=(
                f"Abweichung: lokal {record.status.value}, Broker meldet "
                f"{broker_status.value} (erwartet lokal: {expected_local_status.value})."
            ),
        )

    def reconcile_all(self) -> list[ReconciliationResult]:
        """Vergleicht alle lokal bekannten Orders."""

        return [
            self.reconcile_order(record.client_order_id)
            for record in self._order_repository.all()
        ]

    def reconcile_pending(self) -> list[ReconciliationResult]:
        """Vergleicht nur Orders ohne bereits vom Broker bestätigtes
        Endergebnis (`CREATED`/`SUBMITTED`/`UNKNOWN`, siehe
        `_PENDING_STATUSES`).

        Für einen Session-Neustart relevant: eine Order, die vor einem
        Absturz `SUBMITTED` blieb, ist genau der Fall, den diese Methode
        prüft - eine bereits `FILLED`/`FAILED` gebuchte Order kam direkt
        vom `execute()`-Aufruf und muss nicht erneut beim Broker
        nachgefragt werden.
        """

        return [
            self.reconcile_order(record.client_order_id)
            for record in self._order_repository.all()
            if record.status in _PENDING_STATUSES
        ]
