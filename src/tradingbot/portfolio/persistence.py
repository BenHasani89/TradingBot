"""SQLite-Implementierung des `PortfolioRepository`.

Verwendet ausschliesslich die Standardbibliothek `sqlite3` - kein ORM, keine
Migrationen, keine externe Abhängigkeit.
"""

from __future__ import annotations

import sqlite3

from tradingbot.portfolio.models import PortfolioStatus, Position
from tradingbot.portfolio.repository import PortfolioRepository

_CREATE_CAPITAL_TABLE = """
CREATE TABLE IF NOT EXISTS portfolio_capital (
    portfolio_id TEXT PRIMARY KEY,
    capital REAL NOT NULL
)
"""

_CREATE_POSITION_TABLE = """
CREATE TABLE IF NOT EXISTS portfolio_position (
    portfolio_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    PRIMARY KEY (portfolio_id, symbol)
)
"""


class SqlitePortfolioRepository(PortfolioRepository):
    """Persistiert `PortfolioStatus`-Snapshots in einer SQLite-Datei.

    Jeder `save()`-Aufruf überschreibt den zuvor gespeicherten Zustand für
    die jeweilige `portfolio_id` vollständig und atomar (eine Transaktion:
    alte Positionen löschen, Kapital und neue Positionen einfügen).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        connection = self._connect()
        try:
            with connection:
                connection.execute(_CREATE_CAPITAL_TABLE)
                connection.execute(_CREATE_POSITION_TABLE)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save(self, portfolio_id: str, state: PortfolioStatus) -> None:
        """Speichert `state` als vollständigen, atomaren Snapshot."""

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "DELETE FROM portfolio_position WHERE portfolio_id = ?",
                    (portfolio_id,),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO portfolio_capital (portfolio_id, capital) "
                    "VALUES (?, ?)",
                    (portfolio_id, state.capital),
                )
                connection.executemany(
                    "INSERT INTO portfolio_position "
                    "(portfolio_id, symbol, quantity, entry_price) VALUES (?, ?, ?, ?)",
                    [
                        (
                            portfolio_id,
                            position.symbol,
                            position.quantity,
                            position.entry_price,
                        )
                        for position in state.positions
                    ],
                )
        finally:
            connection.close()

    def load(self, portfolio_id: str) -> PortfolioStatus | None:
        """Lädt den zuletzt gespeicherten Zustand, `None` falls keiner existiert."""

        connection = self._connect()
        try:
            capital_row = connection.execute(
                "SELECT capital FROM portfolio_capital WHERE portfolio_id = ?",
                (portfolio_id,),
            ).fetchone()

            if capital_row is None:
                return None

            position_rows = connection.execute(
                "SELECT symbol, quantity, entry_price FROM portfolio_position "
                "WHERE portfolio_id = ?",
                (portfolio_id,),
            ).fetchall()
        finally:
            connection.close()

        positions = [
            Position(symbol=symbol, quantity=quantity, entry_price=entry_price)
            for symbol, quantity, entry_price in position_rows
        ]
        return PortfolioStatus(capital=capital_row[0], positions=positions)
