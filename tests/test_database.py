from pathlib import Path

from src.database import get_journal_mode, open_database, open_evaluation_database


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"
EVALUATION_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "evaluation_schema.sql"

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


def test_evaluation_database_initialises(tmp_path):
    database_path = tmp_path / "evaluation.db"
    connection = open_evaluation_database(database_path, EVALUATION_SCHEMA_PATH)
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }
        assert mode.lower() == "wal"
        assert "collector_observations" in tables
        assert "collector_rejections" in tables
    finally:
        connection.close()
