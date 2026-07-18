"""SQLite-Implementierung des `SessionRepository`.

Verwendet ausschliesslich die Standardbibliothek `sqlite3` - kein ORM, keine
Migrationen, keine externe Abhängigkeit. Kann dieselbe Datenbankdatei wie
`portfolio.persistence.SqlitePortfolioRepository` und
`risk.persistence.SqliteRiskStateRepository` verwenden (eigene Tabelle
`session`, eigene Klasse, keine gemeinsame Logik).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from tradingbot.paper_trading.repository import SessionRepository
from tradingbot.paper_trading.session import SessionMetadata

_CREATE_SESSION_TABLE = """
CREATE TABLE IF NOT EXISTS session (
    session_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    status TEXT NOT NULL,
    heartbeat_at TEXT
)
"""


class SqliteSessionRepository(SessionRepository):
    """Persistiert `SessionMetadata` in einer SQLite-Datei.

    Jeder `save()`-Aufruf überschreibt einen zuvor gespeicherten Zustand
    für dieselbe `session_id` vollständig und atomar.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        connection = self._connect()
        try:
            with connection:
                connection.execute(_CREATE_SESSION_TABLE)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save(self, session: SessionMetadata) -> None:
        """Speichert `session` als vollständigen, atomaren Snapshot."""

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT OR REPLACE INTO session ("
                    "session_id, symbol, timeframe, strategy_name, "
                    "started_at, stopped_at, status, heartbeat_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session.session_id,
                        session.symbol,
                        session.timeframe,
                        session.strategy_name,
                        session.started_at.isoformat(),
                        session.stopped_at.isoformat() if session.stopped_at else None,
                        session.status,
                        session.heartbeat_at.isoformat() if session.heartbeat_at else None,
                    ),
                )
        finally:
            connection.close()

    def load(self, session_id: str) -> SessionMetadata | None:
        """Lädt die zuletzt gespeicherte Session, `None` falls keine existiert."""

        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT symbol, timeframe, strategy_name, started_at, "
                "stopped_at, status, heartbeat_at FROM session WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        (
            symbol,
            timeframe,
            strategy_name,
            started_at_text,
            stopped_at_text,
            status,
            heartbeat_at_text,
        ) = row

        return SessionMetadata(
            session_id=session_id,
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            started_at=datetime.fromisoformat(started_at_text),
            stopped_at=datetime.fromisoformat(stopped_at_text) if stopped_at_text else None,
            status=status,
            heartbeat_at=datetime.fromisoformat(heartbeat_at_text) if heartbeat_at_text else None,
        )

    def all(self) -> list[SessionMetadata]:
        """Gibt alle gespeicherten Sessions zurück, sortiert nach
        `started_at` (älteste zuerst)."""

        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT session_id, symbol, timeframe, strategy_name, started_at, "
                "stopped_at, status, heartbeat_at FROM session ORDER BY started_at ASC"
            ).fetchall()
        finally:
            connection.close()

        return [
            SessionMetadata(
                session_id=session_id,
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=strategy_name,
                started_at=datetime.fromisoformat(started_at_text),
                stopped_at=datetime.fromisoformat(stopped_at_text) if stopped_at_text else None,
                status=status,
                heartbeat_at=(
                    datetime.fromisoformat(heartbeat_at_text) if heartbeat_at_text else None
                ),
            )
            for (
                session_id,
                symbol,
                timeframe,
                strategy_name,
                started_at_text,
                stopped_at_text,
                status,
                heartbeat_at_text,
            ) in rows
        ]
