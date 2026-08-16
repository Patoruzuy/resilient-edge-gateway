from pathlib import Path

import paho.mqtt.client as mqtt

from src.database import open_database
from src.repository import store_message
from src.upstream import PublicationOutcome, publish_one_pending
from src.validation import parse_telemetry_message

from tests.helpers import valid_message

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


class FakeMessageInfo:
    def __init__(
        self,
        rc=mqtt.MQTT_ERR_SUCCESS,
        mid=1,
        published=True,
        wait_error: Exception | None = None,
    ):
        self.rc = rc
        self.mid = mid
        self._published = published
        self._wait_error = wait_error
        self.timeout = None

    def wait_for_publish(self, timeout=None):
        self.timeout = timeout

        if self._wait_error is not None:
            raise self._wait_error

    def is_published(self):
        return self._published


class FakeMqttClient:
    def __init__(self, message_info):
        self.message_info = message_info
        self.publications = []

    def publish(self, topic, payload, qos, retain):
        self.publications.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retain": retain,
            }
        )
        return self.message_info

def create_pending_message(connection):
    message = parse_telemetry_message(valid_message())

    return store_message(connection, message, "telemetry/sensor-001")

def test_successful_publish_becomes_broker_acknowledged(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = create_pending_message(connection)
        client = FakeMqttClient(
            FakeMessageInfo(
                rc=mqtt.MQTT_ERR_SUCCESS,
                mid=27,
                published=True,
            )
        )
        result = publish_one_pending(
            connection,
            client,
            acknowledgement_timeout_seconds=2.0,
        )
        assert (
            result.outcome
            == PublicationOutcome.BROKER_ACKNOWLEDGED
        )
        assert result.row_id == stored.row_id
        assert result.mqtt_mid == 27

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

        assert row["delivery_state"] == "broker_acknowledged"
        assert row["attempt_count"] == 1
        assert row["acknowledged_at"] is not None

        assert client.publications[0]["qos"] == 1
        assert client.publications[0]["retain"] is False

    finally:
        connection.close()


def test_publish_error_moves_message_to_retry_wait(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = create_pending_message(connection)
        client = FakeMqttClient(
            FakeMessageInfo(
                rc=mqtt.MQTT_ERR_NO_CONN,
                mid=28,
                published=False,
            )
        )
        result = publish_one_pending(connection, client)
        assert result.outcome == PublicationOutcome.RETRY_WAIT

        row = connection.execute(
            """
            SELECT delivery_state, attempt_count
            FROM outbox_messages
            WHERE id = ?
            """,
            (stored.row_id,),
        ).fetchone()

        assert row["delivery_state"] == "retry_wait"
        assert row["attempt_count"] == 1

    finally:
        connection.close()


def test_acknowledgement_timeout_moves_message_to_retry_wait(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        stored = create_pending_message(connection)
        client = FakeMqttClient(
            FakeMessageInfo(
                rc=mqtt.MQTT_ERR_SUCCESS,
                mid=29,
                published=False,
                wait_error=RuntimeError(
                    "Message publish timed out."
                ),
            )
        )
        result = publish_one_pending(connection, client)
        assert result.outcome == PublicationOutcome.RETRY_WAIT

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


def test_no_pending_message_returns_without_publishing(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        client = FakeMqttClient(
            FakeMessageInfo()
        )
        result = publish_one_pending(connection, client)

        assert result.outcome == PublicationOutcome.NO_PENDING
        assert client.publications == []

    finally:
        connection.close()


def test_upstream_publication_preserves_message_identity(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        create_pending_message(connection)
        client = FakeMqttClient(
            FakeMessageInfo(
                rc=mqtt.MQTT_ERR_SUCCESS,
                mid=30,
                published=True,
            )
        )
        publish_one_pending(connection,client)
        forwarded_payload = (client.publications[0]["payload"])
        message = parse_telemetry_message(forwarded_payload)

        assert message.message_id == "msg-000001"
        assert message.device_id == "sensor-001"
        assert message.publisher_session_id == "session-001"
        assert message.source_sequence == 1

    finally:
        connection.close()
