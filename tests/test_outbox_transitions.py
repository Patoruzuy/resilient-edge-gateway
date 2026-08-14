from pathlib import Path

import pytest

from src.database import open_database
from src.repository import (
    get_next_pending_message,
    mark_broker_acknowledged,
    mark_in_flight,
    mark_retry_wait,
    store_message,
)
from src.validation import parse_telemetry_message


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def create_pending_message(connection):
    message = parse_telemetry_message(
        {
            "message_id": "msg-000001",
            "device_id": "sensor-001",
            "publisher_session_id": "session-001",
            "source_sequence": 1,
            "source_timestamp": "2026-07-15T11:00:00Z",
            "priority": 0,
            "payload": {
                "temperature_c": 18.5,
            },
        }
    )

    return store_message(connection, message, "telemetry/sensor-001")


def test_pending_message_can_be_marked_in_flight(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = create_pending_message(connection)
        pending = get_next_pending_message(connection)

        assert pending is not None
        assert pending.row_id == stored.row_id

        mark_in_flight(connection, pending.row_id)

        row = connection.execute(
            """
            SELECT delivery_state, attempt_count, last_attempt_at
            FROM outbox_messages
            WHERE id = ?
            """,
            (pending.row_id,),
        ).fetchone()

        assert row["delivery_state"] == "in_flight"
        assert row["attempt_count"] == 1
        assert row["last_attempt_at"] is not None

    finally:
        connection.close()


def test_in_flight_message_can_be_acknowledged(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = create_pending_message(connection)

        mark_in_flight(connection, stored.row_id)
        mark_broker_acknowledged(connection, stored.row_id)

        row = connection.execute(
            """
            SELECT delivery_state, acknowledged_at
            FROM outbox_messages
            WHERE id = ?
            """,
            (stored.row_id,),
        ).fetchone()

        assert row["delivery_state"] == "broker_acknowledged"
        assert row["acknowledged_at"] is not None

    finally:
        connection.close()


def test_in_flight_message_can_move_to_retry_wait(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = create_pending_message(connection)

        mark_in_flight(connection, stored.row_id)
        mark_retry_wait(connection, stored.row_id)

        row = connection.execute(
            """
            SELECT delivery_state
            FROM outbox_messages
            WHERE id = ?
            """,
            (stored.row_id,),
        ).fetchone()

        assert row["delivery_state"] == "retry_wait"

    finally:
        connection.close()


def test_invalid_transition_is_rejected(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = create_pending_message(connection)
        with pytest.raises(RuntimeError):
            mark_broker_acknowledged(connection, stored.row_id)
    finally:
        connection.close()
