"""Minimale SQLite-Schema-Migration.

Kein generisches Migrations-Framework, kein Rollback-Mechanismus über
mehrere Schritte hinweg - ausschliesslich das bisher tatsächlich
aufgetretene Änderungsmuster: eine neue, nullable Spalte zu einer bereits
existierenden Tabelle hinzufügen (siehe `execution/persistence.py`,
`order_record` hat das bereits zweimal durchlaufen).

`schema_version` ist eine einzige, von allen migrierten Tabellen geteilte
Tabelle (eine Zeile pro `table_name`) - passend zur bestehenden
Architektur unabhängiger Repositories (jedes Repository verwaltet
ausschliesslich seine eigene Zeile, kein zentraler Koordinator nötig).

Robustheit: `apply_column_migrations()` verlässt sich nie blind auf die
gespeicherte Versionsnummer - jede Spalte wird zusätzlich über
`PRAGMA table_info()` auf tatsächliche Existenz geprüft, bevor
`ALTER TABLE` ausgeführt wird. Das macht die Funktion sicher wiederholbar
(Idempotenz), auch wenn eine Tabelle bereits mit dem vollen aktuellen
Schema neu angelegt wurde (dort existieren die Spalten schon, obwohl noch
keine `schema_version`-Zeile geschrieben wurde) oder eine frühere
Migration durch einen Absturz nur teilweise angewendet wurde.

Transaktionssicherheit: Pythons `sqlite3`-Modul behandelt `ALTER TABLE`
(DDL) NICHT automatisch transaktional innerhalb eines `with connection:`-
Blocks - empirisch verifiziert bleiben bereits ausgeführte
`ALTER TABLE`-Anweisungen bei einem `with`-basierten Rollback-Versuch
bestehen (Python startet vor DDL-Anweisungen keine implizite Transaktion,
anders als vor INSERT/UPDATE/DELETE). Diese Funktion öffnet deshalb
bewusst eine explizite Transaktion (`BEGIN` ... `commit()`/`rollback()`)
statt sich auf das implizite Verhalten zu verlassen - bei einem Fehler
mitten in der Migration wird alles zurückgerollt, nie ein halbfertiger
Zwischenzustand dauerhaft gespeichert.
"""

from __future__ import annotations

import sqlite3

_CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    table_name TEXT PRIMARY KEY,
    version INTEGER NOT NULL
)
"""


def _existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")}


def apply_column_migrations(
    connection: sqlite3.Connection,
    table_name: str,
    latest_version: int,
    migrations: dict[int, list[tuple[str, str]]],
) -> None:
    """Bringt `table_name` auf `latest_version`.

    `migrations` bildet die Zielversion, ab der eine Spalte existieren
    soll, auf eine Liste von `(spaltenname, "spaltenname TYP")`-Paaren ab
    - z. B. `{2: [("execution_price", "execution_price REAL")]}` bedeutet
    "ab Version 2 muss die Spalte `execution_price` existieren". Jede
    Spalte wird nur dann per `ALTER TABLE ... ADD COLUMN` ergänzt, wenn
    sie laut `PRAGMA table_info()` tatsächlich fehlt - unabhängig davon,
    was die zuvor gespeicherte Version behauptet.

    `table_name` muss bereits existieren (siehe jeweiliges Repository,
    das die Tabelle vor diesem Aufruf per `CREATE TABLE IF NOT EXISTS`
    mit dem vollen aktuellen Schema anlegt) - für eine brandneue Tabelle
    findet diese Funktion alle Spalten bereits vor und führt keine
    `ALTER TABLE`-Anweisung aus.
    """

    connection.execute(_CREATE_SCHEMA_VERSION_TABLE)

    connection.execute("BEGIN")
    try:
        current_columns = _existing_columns(connection, table_name)

        for version in range(1, latest_version + 1):
            for column_name, column_definition in migrations.get(version, []):
                if column_name not in current_columns:
                    connection.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"
                    )
                    current_columns.add(column_name)

        connection.execute(
            "INSERT OR REPLACE INTO schema_version (table_name, version) VALUES (?, ?)",
            (table_name, latest_version),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
