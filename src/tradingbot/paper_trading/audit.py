"""Minimale, strukturierte Audit-Schicht für Paper-Trading-Sessions.

Verwendet ausschliesslich die Standardbibliothek `sqlite3` - kein ORM,
keine Migrationen. Bewusst ohne ABC: für ein reines Anhängeprotokoll ist
aktuell kein alternatives Backend absehbar (anders als bei Portfolio-/
Risk-State, siehe `portfolio.repository`/`risk.repository`).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


class AuditEventType(Enum):
    """Arten von Ereignissen, die die `PaperTradingEngine` protokolliert."""

    SESSION_STARTED = "session_started"
    SESSION_STOPPED = "session_stopped"
    ORDER_EXECUTED = "order_executed"
    TRADE_BLOCKED = "trade_blocked"
    RISK_EVENT = "risk_event"
    CYCLE_ERROR = "cycle_error"
    RECONCILIATION_MISMATCH = "reconciliation_mismatch"


@dataclass
class AuditEvent:
    """Ein einzelner, unveränderlicher Audit-Eintrag."""

    session_id: str
    event_type: AuditEventType
    message: str
    timestamp: datetime


_CREATE_AUDIT_EVENT_TABLE = """
CREATE TABLE IF NOT EXISTS audit_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL
)
"""


class SqliteAuditLog:
    """Persistiert `AuditEvent`-Einträge append-only in SQLite.

    Kann dieselbe Datenbankdatei wie `SqlitePortfolioRepository`/
    `SqliteRiskStateRepository` verwenden (eigene Tabelle, keine
    gemeinsame Logik).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        connection = self._connect()
        try:
            with connection:
                connection.execute(_CREATE_AUDIT_EVENT_TABLE)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def record(
        self,
        session_id: str,
        event_type: AuditEventType,
        message: str,
        now: datetime | None = None,
    ) -> AuditEvent:
        """Erstellt und speichert einen neuen `AuditEvent`, gibt ihn zurück."""

        event = AuditEvent(
            session_id=session_id,
            event_type=event_type,
            message=message,
            timestamp=now if now is not None else datetime.now(UTC),
        )

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT INTO audit_event "
                    "(session_id, event_type, message, timestamp) VALUES (?, ?, ?, ?)",
                    (
                        event.session_id,
                        event.event_type.value,
                        event.message,
                        event.timestamp.isoformat(),
                    ),
                )
        finally:
            connection.close()

        return event

    def for_session(self, session_id: str) -> list[AuditEvent]:
        """Gibt alle Einträge einer Session zurück, chronologisch aufsteigend."""

        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT session_id, event_type, message, timestamp FROM audit_event "
                "WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        finally:
            connection.close()

        return [
            AuditEvent(
                session_id=row[0],
                event_type=AuditEventType(row[1]),
                message=row[2],
                timestamp=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]
