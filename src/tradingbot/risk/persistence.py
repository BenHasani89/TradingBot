"""SQLite-Implementierung des `RiskStateRepository`.

Verwendet ausschliesslich die Standardbibliothek `sqlite3` - kein ORM, keine
Migrationen, keine externe Abhängigkeit. Kann dieselbe Datenbankdatei wie
`portfolio.persistence.SqlitePortfolioRepository` verwenden (eigene Tabelle
`risk_state`, eigene Klasse, keine gemeinsame Logik mit dem
Portfolio-Repository).
"""

from __future__ import annotations

import sqlite3
from datetime import date

from tradingbot.risk.repository import RiskStateRepository
from tradingbot.risk.risk_state import RiskState

_CREATE_RISK_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS risk_state (
    risk_id TEXT PRIMARY KEY,
    day_start_equity REAL NOT NULL,
    day_start_date TEXT NOT NULL,
    peak_equity REAL NOT NULL,
    kill_switch_active INTEGER NOT NULL,
    kill_switch_reason TEXT,
    daily_loss_blocked INTEGER NOT NULL,
    daily_loss_reason TEXT
)
"""


class SqliteRiskStateRepository(RiskStateRepository):
    """Persistiert `RiskState`-Snapshots in einer SQLite-Datei.

    Jeder `save()`-Aufruf überschreibt den zuvor gespeicherten Zustand für
    die jeweilige `risk_id` vollständig und atomar.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        connection = self._connect()
        try:
            with connection:
                connection.execute(_CREATE_RISK_STATE_TABLE)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save(self, risk_id: str, state: RiskState) -> None:
        """Speichert `state` als vollständigen, atomaren Snapshot."""

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT OR REPLACE INTO risk_state ("
                    "risk_id, day_start_equity, day_start_date, peak_equity, "
                    "kill_switch_active, kill_switch_reason, "
                    "daily_loss_blocked, daily_loss_reason"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        risk_id,
                        state.day_start_equity,
                        state.day_start_date.isoformat(),
                        state.peak_equity,
                        int(state.kill_switch_active),
                        state.kill_switch_reason,
                        int(state.daily_loss_blocked),
                        state.daily_loss_reason,
                    ),
                )
        finally:
            connection.close()

    def load(self, risk_id: str) -> RiskState | None:
        """Lädt den zuletzt gespeicherten Zustand, `None` falls keiner existiert."""

        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT day_start_equity, day_start_date, peak_equity, "
                "kill_switch_active, kill_switch_reason, "
                "daily_loss_blocked, daily_loss_reason "
                "FROM risk_state WHERE risk_id = ?",
                (risk_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        (
            day_start_equity,
            day_start_date_text,
            peak_equity,
            kill_switch_active,
            kill_switch_reason,
            daily_loss_blocked,
            daily_loss_reason,
        ) = row

        return RiskState(
            day_start_equity=day_start_equity,
            day_start_date=date.fromisoformat(day_start_date_text),
            peak_equity=peak_equity,
            kill_switch_active=bool(kill_switch_active),
            kill_switch_reason=kill_switch_reason,
            daily_loss_blocked=bool(daily_loss_blocked),
            daily_loss_reason=daily_loss_reason,
        )
