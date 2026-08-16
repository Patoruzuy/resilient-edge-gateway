from src.database import open_database
from src.repository import (
    mark_broker_acknowledged,
    mark_in_flight,
    mark_retry_wait,
    recover_stale_in_flight,
    store_message,
)
from src.validation import parse_telemetry_message
from tests.helpers import valid_message, SCHEMA_PATH


def _store_test_message(connection, message_id: str, source_sequence: int):
    """Store one unique message for a recovery-state test."""
    data = valid_message()
    data["message_id"] = message_id
    data["source_sequence"] = source_sequence

    message = parse_telemetry_message(data)
    return store_message(connection, message, "telemetry/sensor-001")


def _set_last_attempt_at(connection, row_id: int, timestamp: str) -> None:
    """Set a deterministic attempt timestamp for recovery tests."""
    with connection:
        connection.execute(
            """
            UPDATE outbox_messages
            SET
                last_attempt_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (timestamp, timestamp, row_id),
        )


def test_stale_in_flight_message_moves_to_retry_wait(tmp_path):
    """REC-01: stale in_flight records become recoverable."""
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = _store_test_message(
            connection,
            message_id="recovery-stale-001",
            source_sequence=101,
        )

        mark_in_flight(connection, stored.row_id)

        _set_last_attempt_at(
            connection,
            row_id=stored.row_id,
            timestamp="2026-08-15T10:00:00.000000Z",
        )

        recovered = recover_stale_in_flight(
            connection,
            stale_before="2026-08-15T10:00:30.000000Z",
        )

        row = connection.execute(
            """
            SELECT
                delivery_state,
                attempt_count,
                acknowledged_at
            FROM outbox_messages
            WHERE id = ?
            """,
            (stored.row_id,),
        ).fetchone()

        assert recovered == 1
        assert row["delivery_state"] == "retry_wait"
        assert row["attempt_count"] == 1
        assert row["acknowledged_at"] is None

    finally:
        connection.close()


def test_recent_in_flight_message_is_not_reset(tmp_path):
    """REC-02: a recent publication attempt remains in_flight."""
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = _store_test_message(
            connection,
            message_id="recovery-recent-001",
            source_sequence=102,
        )

        mark_in_flight(connection, stored.row_id)

        _set_last_attempt_at(
            connection,
            row_id=stored.row_id,
            timestamp="2026-08-15T10:01:00.000000Z",
        )

        recovered = recover_stale_in_flight(
            connection,
            stale_before="2026-08-15T10:00:30.000000Z",
        )

        row = connection.execute(
            """
            SELECT
                delivery_state,
                attempt_count
            FROM outbox_messages
            WHERE id = ?
            """,
            (stored.row_id,),
        ).fetchone()

        assert recovered == 0
        assert row["delivery_state"] == "in_flight"
        assert row["attempt_count"] == 1

    finally:
        connection.close()


def test_stale_recovery_does_not_change_other_states(tmp_path):
    """REC-03: only qualifying in_flight records are changed."""
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        pending = _store_test_message(
            connection,
            message_id="recovery-pending-001",
            source_sequence=103,
        )

        retry_wait = _store_test_message(
            connection,
            message_id="recovery-retry-001",
            source_sequence=104,
        )
        mark_in_flight(connection, retry_wait.row_id)
        mark_retry_wait(connection, retry_wait.row_id)

        acknowledged = _store_test_message(
            connection,
            message_id="recovery-ack-001",
            source_sequence=105,
        )
        mark_in_flight(connection, acknowledged.row_id)
        mark_broker_acknowledged(connection, acknowledged.row_id)

        recovered = recover_stale_in_flight(
            connection,
            stale_before="2099-01-01T00:00:00.000000Z",
        )

        rows = connection.execute(
            """
            SELECT
                id,
                delivery_state
            FROM outbox_messages
            WHERE id IN (?, ?, ?)
            """,
            (
                pending.row_id,
                retry_wait.row_id,
                acknowledged.row_id,
            ),
        ).fetchall()

        states = {
            int(row["id"]): str(row["delivery_state"])
            for row in rows
        }

        assert recovered == 0
        assert states[pending.row_id] == "pending"
        assert states[retry_wait.row_id] == "retry_wait"
        assert states[acknowledged.row_id] == "broker_acknowledged"

    finally:
        connection.close()


def test_stale_in_flight_recovery_survives_database_reopening(tmp_path):
    """REC-04: local persistence allows recovery after reopening."""
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    stored = _store_test_message(
        connection,
        message_id="recovery-restart-001",
        source_sequence=106,
    )

    mark_in_flight(connection, stored.row_id)

    _set_last_attempt_at(
        connection,
        row_id=stored.row_id,
        timestamp="2026-08-15T09:00:00.000000Z",
    )

    connection.close()

    reopened = open_database(database_path, SCHEMA_PATH)

    try:
        before = reopened.execute(
            """
            SELECT
                delivery_state,
                attempt_count
            FROM outbox_messages
            WHERE id = ?
            """,
            (stored.row_id,),
        ).fetchone()

        assert before["delivery_state"] == "in_flight"
        assert before["attempt_count"] == 1

        recovered = recover_stale_in_flight(
            reopened,
            stale_before="2026-08-15T09:00:30.000000Z",
        )

        after = reopened.execute(
            """
            SELECT
                delivery_state,
                attempt_count
            FROM outbox_messages
            WHERE id = ?
            """,
            (stored.row_id,),
        ).fetchone()

        assert recovered == 1
        assert after["delivery_state"] == "retry_wait"
        assert after["attempt_count"] == 1

    finally:
        reopened.close()
