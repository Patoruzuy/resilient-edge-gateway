from pathlib import Path

from src.database import open_database
from src.repository import StoreOutcome, store_message
from src.validation import parse_telemetry_message


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def valid_message(payload: dict | None = None) -> dict:
    return {
        "message_id": "msg-000001",
        "device_id": "sensor-001",
        "publisher_session_id": "session-001",
        "source_sequence": 1,
        "source_timestamp": "2026-07-15T11:00:00Z",
        "priority": 0,
        "payload": payload or {"temperature_c": 18.5},
    }


def test_new_message_is_inserted_as_pending(tmp_path):
    connection = open_database(
        tmp_path / "gateway.db",
        SCHEMA_PATH,
    )

    try:
        message = parse_telemetry_message(valid_message())

        result = store_message(
            connection,
            message,
            topic="telemetry/sensor-001",
        )

        assert result.outcome == StoreOutcome.INSERTED

        row = connection.execute(
            """
            SELECT delivery_state, attempt_count
            FROM outbox_messages
            WHERE id = ?
            """,
            (result.row_id,),
        ).fetchone()

        assert row["delivery_state"] == "pending"
        assert row["attempt_count"] == 0
    finally:
        connection.close()


def test_identical_retransmission_is_duplicate(tmp_path):
    connection = open_database(
        tmp_path / "gateway.db",
        SCHEMA_PATH,
    )

    try:
        message = parse_telemetry_message(valid_message())

        first = store_message(
            connection,
            message,
            "telemetry/sensor-001",
        )
        second = store_message(
            connection,
            message,
            "telemetry/sensor-001",
        )

        assert first.outcome == StoreOutcome.INSERTED
        assert second.outcome == StoreOutcome.DUPLICATE
        assert first.row_id == second.row_id

        count = connection.execute(
            "SELECT COUNT(*) FROM outbox_messages"
        ).fetchone()[0]

        assert count == 1
    finally:
        connection.close()


def test_same_key_with_different_payload_is_conflict(tmp_path):
    connection = open_database(
        tmp_path / "gateway.db",
        SCHEMA_PATH,
    )

    try:
        first_message = parse_telemetry_message(
            valid_message({"temperature_c": 18.5})
        )
        conflicting_message = parse_telemetry_message(
            {
                **valid_message({"temperature_c": 27.0}),
                "message_id": "msg-000002",
            }
        )

        first = store_message(
            connection,
            first_message,
            "telemetry/sensor-001",
        )
        conflict = store_message(
            connection,
            conflicting_message,
            "telemetry/sensor-001",
        )

        assert first.outcome == StoreOutcome.INSERTED
        assert conflict.outcome == StoreOutcome.CONFLICT

        count = connection.execute(
            "SELECT COUNT(*) FROM outbox_messages"
        ).fetchone()[0]

        assert count == 1
    finally:
        connection.close()


def test_committed_message_survives_reopening(tmp_path):
    database_path = tmp_path / "gateway.db"

    first_connection = open_database(
        database_path,
        SCHEMA_PATH,
    )

    message = parse_telemetry_message(valid_message())

    result = store_message(
        first_connection,
        message,
        "telemetry/sensor-001",
    )
    first_connection.close()

    second_connection = open_database(
        database_path,
        SCHEMA_PATH,
    )

    try:
        row = second_connection.execute(
            """
            SELECT message_id, delivery_state
            FROM outbox_messages
            WHERE id = ?
            """,
            (result.row_id,),
        ).fetchone()

        assert row is not None
        assert row["message_id"] == "msg-000001"
        assert row["delivery_state"] == "pending"
    finally:
        second_connection.close()
