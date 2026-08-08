from pathlib import Path
import json

from src.database import open_database
from src.ingestion import (
    IngestionOutcome,
    process_mqtt_publication,
)


SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schema.sql"
)


def valid_payload():
    return json.dumps(
    {
        "message_id": "msg-000001",
        "device_id": "sensor-001",
        "publisher_session_id": "session-001",
        "source_sequence": 1,
        "source_timestamp": "2026-07-15T12:00:00+01:00",
        "priority": 0,
        "payload": {
            "temperature_c": 18.5,
            "humidity_percent": 71,
        },
    }).encode("utf-8")


def test_valid_mqtt_publication_is_persisted(tmp_path):
    connection = open_database(
        tmp_path / "gateway.db",
        SCHEMA_PATH,
    )

    try:
        result = process_mqtt_publication(
            connection=connection,
            topic="telemetry/sensor-001",
            payload=valid_payload(),
        )

        assert result.outcome == IngestionOutcome.INSERTED

        row = connection.execute(
            """
            SELECT message_id, topic, delivery_state
            FROM outbox_messages
            """
        ).fetchone()

        assert row["message_id"] == "msg-000001"
        assert row["topic"] == "telemetry/sensor-001"
        assert row["delivery_state"] == "pending"

    finally:
        connection.close()


def test_malformed_json_is_rejected(tmp_path):
    connection = open_database(
        tmp_path / "gateway.db",
        SCHEMA_PATH,
    )

    try:
        result = process_mqtt_publication(
            connection=connection,
            topic="telemetry/sensor-001",
            payload=b"{not-json}",
        )

        assert result.outcome == IngestionOutcome.REJECTED
        assert result.reason_code == "invalid_json"

        count = connection.execute(
            "SELECT COUNT(*) FROM outbox_messages"
        ).fetchone()[0]

        assert count == 0

    finally:
        connection.close()


def test_identical_publication_is_classified_as_duplicate(tmp_path):
    connection = open_database(
        tmp_path / "gateway.db",
        SCHEMA_PATH,
    )

    try:
        first = process_mqtt_publication(
            connection,
            "telemetry/sensor-001",
            valid_payload(),
        )
        second = process_mqtt_publication(
            connection,
            "telemetry/sensor-001",
            valid_payload(),
        )

        assert first.outcome == IngestionOutcome.INSERTED
        assert second.outcome == IngestionOutcome.DUPLICATE

        count = connection.execute(
            "SELECT COUNT(*) FROM outbox_messages"
        ).fetchone()[0]

        assert count == 1

    finally:
        connection.close()
