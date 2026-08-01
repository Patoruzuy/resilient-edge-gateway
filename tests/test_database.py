from pathlib import Path

from src.database import (
    get_journal_mode,
    open_database,
)


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def test_database_initialises_with_wal(tmp_path):
    database_path = tmp_path / "gateway.db"

    connection = open_database(database_path, SCHEMA_PATH)

    try:
        assert get_journal_mode(connection) == "wal"

        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'outbox_messages'
            """
        ).fetchone()

        assert table is not None
    finally:
        connection.close()
