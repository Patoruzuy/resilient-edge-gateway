import json
from pathlib import Path

from src.database import open_database, open_evaluation_database
from src.repository import StoreOutcome, store_message, record_collector_observation
from src.validation import parse_telemetry_message


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"
EVALUATION_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "evaluation_schema.sql"


def valid_message(payload: dict | None = None) -> dict:
    """Retunrs a valid telemetry message as dict."""
    return {
        "message_id": "msg-000001",
        "device_id": "sensor-001",
        "publisher_session_id": "session-001",
        "source_sequence": 1,
        "source_timestamp": "2026-07-15T11:00:00Z",
        "priority": 0,
        "payload": payload or {"temperature_c": 18.5},
    }

def valid_message_bytes() -> bytes:
    """Return the valid telemetry message as the MQTT-style UTF-8 bytes"""
    return json.dumps(
        valid_message(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

def test_new_message_is_inserted_as_pending(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        message = parse_telemetry_message(valid_message())
        result = store_message(connection, message, topic="telemetry/sensor-001")

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
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        message = parse_telemetry_message(valid_message())
        first = store_message(connection, message, "telemetry/sensor-001")
        second = store_message(connection, message, "telemetry/sensor-001")

        assert first.outcome == StoreOutcome.INSERTED
        assert second.outcome == StoreOutcome.DUPLICATE
        assert first.row_id == second.row_id

        count = connection.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0]

        assert count == 1
    finally:
        connection.close()


def test_same_key_with_different_payload_is_conflict(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

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

        first = store_message(connection, first_message, "telemetry/sensor-001")
        conflict = store_message(
            connection,
            conflicting_message,
            "telemetry/sensor-001",
        )
        assert first.outcome == StoreOutcome.INSERTED
        assert conflict.outcome == StoreOutcome.CONFLICT

        count = connection.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0]

        assert count == 1
    finally:
        connection.close()


def test_committed_message_survives_reopening(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    message = parse_telemetry_message(valid_message())
    result = store_message(connection, message, "telemetry/sensor-001")
    connection.close()

    second_connection = open_database(database_path, SCHEMA_PATH)
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


def test_collector_preserves_repeated_observations(tmp_path):
    database_path = tmp_path / "evaluation.db"
    connection = open_evaluation_database(database_path, EVALUATION_SCHEMA_PATH)

    try:
        message = parse_telemetry_message(valid_message())
        record_collector_observation(
            connection,
            run_id="run-001",
            topic="telemetry/sensor-001",
            qos=1,
            retained=False,
            mqtt_duplicate=False,
            raw_message=valid_message_bytes(),
            message=message,
        )

        record_collector_observation(
            connection,
            run_id="run-001",
            topic="telemetry/sensor-001",
            qos=1,
            retained=False,
            mqtt_duplicate=True,
            raw_message=valid_message_bytes(),
            message=message,
        )
        rows = connection.execute(
            """
            SELECT
                message_id,
                mqtt_duplicate
            FROM collector_observations
            WHERE run_id = ?
            ORDER BY id
            """,
            ("run-001",),
        ).fetchall()

        assert len(rows) == 2

        assert rows[0]["message_id"] == "msg-000001"
        assert rows[1]["message_id"] == "msg-000001"

        assert rows[0]["mqtt_duplicate"] == 0
        assert rows[1]["mqtt_duplicate"] == 1

    finally:
        connection.close()
