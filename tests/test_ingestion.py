from pathlib import Path

from tests.helpers import valid_payload
from src.database import open_database
from src.ingestion import (
    IngestionOutcome,
    process_mqtt_publication,
)


SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schema.sql"
)

def test_valid_mqtt_publication_is_persisted(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

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
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

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
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

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
