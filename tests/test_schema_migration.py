import sqlite3

import pytest

from tradingbot.schema_migration import apply_column_migrations

_MIGRATIONS: dict[int, list[tuple[str, str]]] = {
    2: [("extra", "extra REAL")],
    3: [("extra2", "extra2 TEXT")],
}


def _connect(tmp_path) -> sqlite3.Connection:

    return sqlite3.connect(str(tmp_path / "test.sqlite3"))


def _create_old_table(connection: sqlite3.Connection) -> None:
    """Simuliert eine Tabelle im ursprünglichen Schema (Version 1) -
    ohne die später hinzugekommenen Spalten `extra`/`extra2`."""

    connection.execute("CREATE TABLE t (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.commit()


def _create_full_table(connection: sqlite3.Connection) -> None:
    """Simuliert eine brandneue Tabelle, direkt mit dem vollen aktuellen
    Schema angelegt (wie es `CREATE TABLE IF NOT EXISTS` in den echten
    Repositories für eine neue Datenbank tut)."""

    connection.execute(
        "CREATE TABLE t (id TEXT PRIMARY KEY, value TEXT NOT NULL, extra REAL, extra2 TEXT)"
    )
    connection.commit()


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:

    return {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")}


def _schema_version(connection: sqlite3.Connection, table_name: str):

    row = connection.execute(
        "SELECT version FROM schema_version WHERE table_name = ?", (table_name,)
    ).fetchone()
    return row[0] if row is not None else None


# --- Alte Tabelle wird migriert ---------------------------------------------------------------


def test_old_table_without_new_columns_is_migrated(tmp_path):

    connection = _connect(tmp_path)
    _create_old_table(connection)

    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)

    assert _columns(connection, "t") == {"id", "value", "extra", "extra2"}


def test_old_table_data_survives_migration(tmp_path):

    connection = _connect(tmp_path)
    _create_old_table(connection)
    connection.execute("INSERT INTO t (id, value) VALUES ('order-1', 'hello')")
    connection.commit()

    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)

    row = connection.execute("SELECT id, value, extra, extra2 FROM t").fetchone()
    assert row == ("order-1", "hello", None, None)


def test_partially_migrated_table_only_gets_missing_column():
    """Tabelle hat bereits eine Spalte aus einer früher nur teilweise
    angewendeten Migration - apply_column_migrations darf diese nicht
    doppelt hinzufügen, muss aber die fehlende Spalte ergänzen."""

    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE t (id TEXT PRIMARY KEY, value TEXT NOT NULL, extra REAL)")
    connection.commit()

    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)

    assert _columns(connection, "t") == {"id", "value", "extra", "extra2"}


# --- Neue Datenbank funktioniert ---------------------------------------------------------------


def test_new_table_already_has_all_columns_needs_no_alter(tmp_path):

    connection = _connect(tmp_path)
    _create_full_table(connection)

    # Darf keine Exception werfen (kein "duplicate column name"), obwohl
    # die Spalten bereits existieren.
    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)

    assert _columns(connection, "t") == {"id", "value", "extra", "extra2"}
    assert _schema_version(connection, "t") == 3


# --- Idempotenz ----------------------------------------------------------------------------


def test_migration_is_idempotent_on_old_table(tmp_path):

    connection = _connect(tmp_path)
    _create_old_table(connection)

    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)
    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)

    assert _columns(connection, "t") == {"id", "value", "extra", "extra2"}
    assert _schema_version(connection, "t") == 3


def test_migration_is_idempotent_on_new_table(tmp_path):

    connection = _connect(tmp_path)
    _create_full_table(connection)

    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)
    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)

    assert _columns(connection, "t") == {"id", "value", "extra", "extra2"}


# --- schema_version korrekt gesetzt -----------------------------------------------------------


def test_schema_version_is_written_correctly(tmp_path):

    connection = _connect(tmp_path)
    _create_old_table(connection)

    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)

    assert _schema_version(connection, "t") == 3


def test_schema_version_tracks_multiple_tables_independently(tmp_path):

    connection = _connect(tmp_path)
    _create_old_table(connection)
    connection.execute("CREATE TABLE other (id TEXT PRIMARY KEY)")
    connection.commit()

    apply_column_migrations(connection, "t", latest_version=3, migrations=_MIGRATIONS)
    apply_column_migrations(connection, "other", latest_version=1, migrations={})

    assert _schema_version(connection, "t") == 3
    assert _schema_version(connection, "other") == 1


# --- Transaktionssicherheit --------------------------------------------------------------------


def test_migration_rolls_back_completely_on_failure(tmp_path):
    """Bricht eine Migration mitten in der Transaktion ab, darf kein
    halbfertiger Zustand bestehen bleiben - weder die vorherige (gültige)
    Spalte noch die schema_version-Zeile."""

    connection = _connect(tmp_path)
    _create_old_table(connection)

    broken_migrations: dict[int, list[tuple[str, str]]] = {
        2: [("extra", "extra REAL")],
        # ALTER TABLE ... ADD COLUMN mit PRIMARY KEY ist in SQLite
        # explizit nicht erlaubt - erzwingt zuverlässig einen Fehler
        # nach der bereits erfolgreichen Version-2-Spalte.
        3: [("extra2", "extra2 TEXT PRIMARY KEY")],
    }

    with pytest.raises(sqlite3.OperationalError):
        apply_column_migrations(connection, "t", latest_version=3, migrations=broken_migrations)

    assert _columns(connection, "t") == {"id", "value"}
    assert _schema_version(connection, "t") is None
