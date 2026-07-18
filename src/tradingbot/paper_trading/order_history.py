"""Strukturierte, persistente Order-Historie für Paper-Trading-Sessions.

Ergänzt die freitextigen Audit-Events (`paper_trading.audit`) um
strukturierte, auswertbare Order-Datensätze. Verwendet ausschliesslich die
Standardbibliothek `sqlite3` - kein ORM, kein ABC (kein alternatives
Backend absehbar, analog zu `SqliteAuditLog`).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass
class OrderExecution:
    """Ein einzelner, strukturierter Order-Ausführungs-Datensatz.

    `session_id` ist bewusst kein Feld dieser Klasse (analog zu
    `PortfolioStatus`/`RiskState`) - die Zuordnung übernimmt
    `SqliteOrderHistory` über den expliziten `session_id`-Parameter.
    """

    timestamp: datetime
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float
    success: bool


_CREATE_ORDER_EXECUTION_TABLE = """
CREATE TABLE IF NOT EXISTS order_execution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL,
    success INTEGER NOT NULL
)
"""


def _row_to_execution(row: tuple) -> OrderExecution:

    timestamp, symbol, side, quantity, price, fee, success = row
    return OrderExecution(
        timestamp=datetime.fromisoformat(timestamp),
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        fee=fee,
        success=bool(success),
    )


class SqliteOrderHistory:
    """Persistiert `OrderExecution`-Einträge append-only in SQLite, je
    `session_id`."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        connection = self._connect()
        try:
            with connection:
                connection.execute(_CREATE_ORDER_EXECUTION_TABLE)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def append(self, session_id: str, execution: OrderExecution) -> None:
        """Fügt einen Order-Ausführungs-Datensatz an (append-only, keine
        Überschreibung bestehender Einträge)."""

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT INTO order_execution "
                    "(session_id, timestamp, symbol, side, quantity, price, fee, success) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        execution.timestamp.isoformat(),
                        execution.symbol,
                        execution.side,
                        execution.quantity,
                        execution.price,
                        execution.fee,
                        int(execution.success),
                    ),
                )
        finally:
            connection.close()

    def all(self, session_id: str) -> list[OrderExecution]:
        """Gibt alle Order-Ausführungen einer Session zurück, chronologisch
        aufsteigend."""

        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT timestamp, symbol, side, quantity, price, fee, success "
                "FROM order_execution WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        finally:
            connection.close()

        return [_row_to_execution(row) for row in rows]

    def latest(self, session_id: str) -> OrderExecution | None:
        """Gibt die zuletzt ausgeführte Order einer Session zurück, `None`
        falls noch keine existiert."""

        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT timestamp, symbol, side, quantity, price, fee, success "
                "FROM order_execution WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()

        return _row_to_execution(row) if row is not None else None
