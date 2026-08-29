"""
SQLite initialisation for the local-first edge gateway.

This module creates or open the gateway database,
verifies tht WAL mode is active and return a configured connection.
"""

import sqlite3
from pathlib import Path  # Decide to use Path over os because is more readable


def get_journal_mode(connection: sqlite3.Connection) -> str:
    """
    Query SQLite runtime settings using PRAGMA statement to
    confirm that WAL mode is active.
    """
    row = connection.execute("PRAGMA journal_mode").fetchone()
    if row is None:
        raise RuntimeError("SQLite did not return a journal mode")
    # SQLite always returns a row ['wal']
    return str(row[0]).lower()


def open_database(database_path: str | Path, schema_path: str | Path) -> sqlite3.Connection:
    """
    Open and initialise the gateway database.

    A new database is created from the file schema.sql. WAL mode and
    foreign-key are verified before the connection is returned.
    """
    database_path = Path(database_path)
    schema_path = Path(schema_path)
    if not schema_path.is_file():
        raise RuntimeError(f"Schema file does not exist: {schema_path}")

    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        # These settings apply to each SQLite connection
        # SQLite foreign-key enforced per connection, so it must
        # be enabled whenever the gateway opens the database.
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        # Attempts to change the mode
        connection.execute("PRAGMA journal_mode = WAL")

        if get_journal_mode(connection) != "wal":
            raise RuntimeError("SQLite WAL mode could not be enabled")
        # Ensure the schema exists in the database.
        schema_sql = schema_path.read_text(encoding="utf-8")
        connection.executescript(schema_sql)
        # Query and it returns 1 when enforcement is active and 0 when disabled.
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
        if foreign_keys is None or int(foreign_keys[0]) != 1:
            raise RuntimeError("SQLite foreign-keys enforcement is not active")

        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
                AND name = 'outbox_messages'
            """
        ).fetchone()

        if table is None:
            raise RuntimeError("Required outbox_messages table was not created")

        return connection
    except Exception:
        connection.close()
        raise

def open_evaluation_database(database_path: Path, schema_path: Path) -> sqlite3.Connection:
    """
    Open and initialise the independent evaluation database.
    Evaluation evidence is stored separately from gateway operational
    state so that measurement records do not affect the system being
    evaluated.
    """
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path,timeout=5.0,)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        # Ensure the schema exists in the database.
        schema_sql = schema_path.read_text(encoding="utf-8")
        connection.executescript(schema_sql)
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        if str(journal_mode).lower() != "wal":
            raise RuntimeError("Evaluation database is not using WAL mode.")
        return connection

    except Exception:
        connection.close()
        raise
