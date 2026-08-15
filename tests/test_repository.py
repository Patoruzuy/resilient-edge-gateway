from pathlib import Path
import json

from src.database import open_database, open_evaluation_database
from src.repository import (
    StoreOutcome,
    store_message,
    record_collector_observation,
    get_gateway_duplicate_summary,
    get_collector_duplicate_summary,
)
from src.validation import parse_telemetry_message
from tests.helpers import valid_message, valid_message_bytes


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"
EVALUATION_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "evaluation_schema.sql"

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

        count = connection.execute(
            "SELECT COUNT(*) FROM outbox_messages"
            ).fetchone()[0]

        assert count == 1
        # this cover DUP-01: expected retransmission
        observation = connection.execute(
            """
            SELECT
                classification,
                stored_payload_hash,
                observed_payload_hash
            FROM gateway_duplicate_observations
            """
        ).fetchone()

        assert observation is not None
        assert observation["classification"] == "expected_retransmission"
        assert observation["stored_payload_hash"] == observation["observed_payload_hash"]

        summary = get_gateway_duplicate_summary(
            connection
        )
        assert summary.expected_retransmissions == 1
        assert summary.payload_conflicts == 0
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
        conflict = store_message(connection, conflicting_message,"telemetry/sensor-001")
        assert first.outcome == StoreOutcome.INSERTED
        assert conflict.outcome == StoreOutcome.CONFLICT

        count = connection.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0]

        assert count == 1
        # This cover DUP-02: payload conflict
        observation = connection.execute(
            """
            SELECT
                classification,
                stored_payload_hash,
                observed_payload_hash
            FROM gateway_duplicate_observations
            """
        ).fetchone()

        assert observation is not None
        assert observation["classification"] == "payload_conflict"
        assert observation["stored_payload_hash"] != observation["observed_payload_hash"]

        summary = get_gateway_duplicate_summary(
            connection
        )
        assert summary.expected_retransmissions == 0
        assert summary.payload_conflicts == 1

        # Checks that the original payload has not been overwritten
        stored = connection.execute(
            """
            SELECT payload
            FROM outbox_messages
            WHERE id = ?
            """,
            (first.row_id,),
        ).fetchone()

        assert stored is not None
        assert json.loads(stored["payload"]) == {"temperature_c": 18.5}
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

        summary = get_collector_duplicate_summary(
            connection,
            run_id="run-001",
        )
        # This cover DUP-03 collector repeated messages
        assert summary.total_observations == 2
        assert summary.unique_identities == 1
        assert summary.repeated_observations == 1
        assert summary.conflicting_observations == 0

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

def test_collector_identifies_conflicting_observation(
    tmp_path,
):
    connection = open_evaluation_database(
        tmp_path / "evaluation.db",
        EVALUATION_SCHEMA_PATH,
    )

    try:
        original_data = valid_message()

        conflicting_data = valid_message()
        conflicting_data["payload"] = {
            "temperature_c": 25.0,
        }

        original = parse_telemetry_message(
            original_data
        )

        conflicting = parse_telemetry_message(
            conflicting_data
        )
        record_collector_observation(
            connection,
            run_id="conflict-run-001",
            topic="telemetry/sensor-001",
            qos=1,
            retained=False,
            mqtt_duplicate=False,
            raw_message=valid_message_bytes(original_data),
            message=original,
        )

        record_collector_observation(
            connection,
            run_id="conflict-run-001",
            topic="telemetry/sensor-001",
            qos=1,
            retained=False,
            mqtt_duplicate=False,
            raw_message=valid_message_bytes(conflicting_data),
            message=conflicting,
        )
        summary = get_collector_duplicate_summary(
            connection,
            run_id="conflict-run-001",
        )

        assert summary.total_observations == 2
        assert summary.unique_identities == 1
        assert summary.repeated_observations == 0
        assert summary.conflicting_observations == 1

    finally:
        connection.close()
