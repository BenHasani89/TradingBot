"""Repository-Schnittstelle für die Persistenz von Order-Lifecycle-Zuständen."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from tradingbot.execution.models import ExecutionResult, Order, OrderStatus


@dataclass
class OrderRecord:
    """Der Lifecycle-Zustand einer einzelnen Order im `OrderManager`.

    Fasst die ursprüngliche `Order`, ihren aktuellen `OrderStatus` und -
    sobald vorhanden - das `ExecutionResult` der Broker-Ausführung
    zusammen. `execution_result` ist `None`, solange die Order noch keinen
    Endzustand erreicht hat (`CREATED`/`SUBMITTED`). Der zentrale
    Datensatz für Duplicate Detection (`client_order_id`) und künftige
    Reconciliation.
    """

    client_order_id: str
    order: Order
    status: OrderStatus
    execution_result: ExecutionResult | None = None


class OrderRepository(ABC):
    """Abstrakte Persistenz-Schnittstelle für `OrderRecord`.

    Kennt ausschliesslich das Speichern/Laden eines Order-Lifecycle-
    Zustands anhand seiner `client_order_id` - keine Kenntnis von
    Portfolio-, Risk- oder Session-Konzepten.
    """

    @abstractmethod
    def save(self, order_record: OrderRecord) -> None:
        """Speichert `order_record` unter seiner `client_order_id`.

        Ein erneuter `save()`-Aufruf mit derselben `client_order_id`
        überschreibt den zuvor gespeicherten Zustand vollständig
        (Lifecycle-Übergang, kein neuer, separater Datensatz).
        """

    @abstractmethod
    def get(self, client_order_id: str) -> OrderRecord | None:
        """Lädt den `OrderRecord` zu `client_order_id`.

        Gibt `None` zurück, wenn dafür noch nichts gespeichert wurde.
        """

    @abstractmethod
    def all(self) -> list[OrderRecord]:
        """Gibt alle gespeicherten `OrderRecord`-Einträge zurück."""


class InMemoryOrderRepository(OrderRepository):
    """Reine In-Memory-Implementierung ohne Persistenz.

    Standard-Repository für den `OrderManager`, den `TradingOrchestrator`
    intern aufbaut (siehe `core/orchestrator.py`) - dadurch lösen
    Backtest-/Research-Läufe (die `TradingOrchestrator` unverändert
    wiederverwenden) keine SQLite-Schreibvorgänge pro simuliertem Trade
    aus. Für dauerhafte Nachverfolgung (Paper/Live Trading) steht
    `SqliteOrderRepository` (siehe `execution/persistence.py`) zur
    Verfügung.
    """

    def __init__(self) -> None:
        self._records: dict[str, OrderRecord] = {}

    def save(self, order_record: OrderRecord) -> None:
        self._records[order_record.client_order_id] = order_record

    def get(self, client_order_id: str) -> OrderRecord | None:
        return self._records.get(client_order_id)

    def all(self) -> list[OrderRecord]:
        return list(self._records.values())
