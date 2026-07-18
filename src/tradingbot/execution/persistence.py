"""SQLite-Implementierung des `OrderRepository`.

Verwendet ausschliesslich die Standardbibliothek `sqlite3` - kein ORM, keine
Migrationen, keine externe Abhängigkeit. Für dauerhafte Order-Nachverfolgung
(Paper/Live Trading) - der `TradingOrchestrator` selbst verwendet intern
`InMemoryOrderRepository` (siehe `execution/order_repository.py`), damit
Backtest-Läufe keine SQLite-Schreibvorgänge auslösen.
"""

from __future__ import annotations

import sqlite3

from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_repository import OrderRecord, OrderRepository

_CREATE_ORDER_RECORD_TABLE = """
CREATE TABLE IF NOT EXISTS order_record (
    client_order_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    execution_success INTEGER,
    execution_message TEXT,
    execution_fee REAL,
    execution_slippage REAL,
    execution_status TEXT,
    execution_broker_order_id TEXT
)
"""

_SELECT_COLUMNS = (
    "client_order_id, symbol, side, quantity, price, status, "
    "execution_success, execution_message, execution_fee, execution_slippage, "
    "execution_status, execution_broker_order_id"
)


def _row_to_record(row: tuple) -> OrderRecord:

    (
        client_order_id,
        symbol,
        side,
        quantity,
        price,
        status,
        execution_success,
        execution_message,
        execution_fee,
        execution_slippage,
        execution_status,
        execution_broker_order_id,
    ) = row

    order = Order(
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        client_order_id=client_order_id,
    )

    execution_result = None
    if execution_success is not None:
        execution_result = ExecutionResult(
            success=bool(execution_success),
            order=order,
            message=execution_message,
            fee=execution_fee,
            slippage=execution_slippage,
            status=ExecutionStatus(execution_status),
            broker_order_id=execution_broker_order_id,
        )

    return OrderRecord(
        client_order_id=client_order_id,
        order=order,
        status=OrderStatus(status),
        execution_result=execution_result,
    )


class SqliteOrderRepository(OrderRepository):
    """Persistiert `OrderRecord`-Einträge in SQLite, je `client_order_id`.

    Jeder `save()`-Aufruf überschreibt einen zuvor gespeicherten Zustand
    für dieselbe `client_order_id` vollständig und atomar (Lifecycle-
    Übergang, kein neuer Datensatz).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        connection = self._connect()
        try:
            with connection:
                connection.execute(_CREATE_ORDER_RECORD_TABLE)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save(self, order_record: OrderRecord) -> None:
        """Speichert `order_record` als vollständigen, atomaren Snapshot."""

        execution_result = order_record.execution_result

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT OR REPLACE INTO order_record ("
                    "client_order_id, symbol, side, quantity, price, status, "
                    "execution_success, execution_message, execution_fee, "
                    "execution_slippage, execution_status, execution_broker_order_id"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        order_record.client_order_id,
                        order_record.order.symbol,
                        order_record.order.side,
                        order_record.order.quantity,
                        order_record.order.price,
                        order_record.status.value,
                        int(execution_result.success) if execution_result else None,
                        execution_result.message if execution_result else None,
                        execution_result.fee if execution_result else None,
                        execution_result.slippage if execution_result else None,
                        execution_result.status.value if execution_result else None,
                        execution_result.broker_order_id if execution_result else None,
                    ),
                )
        finally:
            connection.close()

    def get(self, client_order_id: str) -> OrderRecord | None:
        """Lädt den `OrderRecord` zu `client_order_id`, `None` falls keiner existiert."""

        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM order_record "  # noqa: S608 - fester Spaltenname, kein Nutzereingabewert
                "WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
        finally:
            connection.close()

        return _row_to_record(row) if row is not None else None

    def all(self) -> list[OrderRecord]:
        """Gibt alle gespeicherten `OrderRecord`-Einträge zurück, in
        Einfüge-Reihenfolge."""

        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM order_record "  # noqa: S608 - fester Spaltenname, kein Nutzereingabewert
                "ORDER BY rowid ASC"
            ).fetchall()
        finally:
            connection.close()

        return [_row_to_record(row) for row in rows]
