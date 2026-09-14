import paho.mqtt.client as mqtt

from src.controlled_recovery import (
    publish_health_probe,
    publish_recovery_batch,
    wait_for_link_stability,
)
from src.database import open_database
from src.repository import (
    get_next_recovery_message,
    mark_broker_acknowledged,
    mark_recovery_in_flight,
    mark_retry_wait,
    store_message,
)
from src.validation import parse_telemetry_message
from tests.helpers import valid_message, SCHEMA_PATH


class FakeMessageInfo:
    def __init__(
        self,
        rc=mqtt.MQTT_ERR_SUCCESS,
        mid=1,
        published=True,
        wait_error=None,
    ):
        self.rc = rc
        self.mid = mid
        self._published = published
        self._wait_error = wait_error

    def wait_for_publish(self, timeout=None):
        del timeout

        if self._wait_error is not None:
            raise self._wait_error

    def is_published(self):
        return self._published


class FakeMqttClient:
    def __init__(self, infos=None, *, connected=True):
        self.infos = list(infos or [])
        self.connected = connected
        self.publications = []

    def is_connected(self):
        return self.connected

    def publish(self, topic, payload, qos, retain):
        self.publications.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retain": retain,
            }
        )

        if not self.infos:
            raise AssertionError("No FakeMessageInfo remains for this publication.")
        return self.infos.pop(0)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def add_message(
    connection,
    sequence,
    message_id=None,
    device_id="sensor-001",
    session_id="session-001",
    priority=0,
):
    data = valid_message()
    data["message_id"] = message_id or f"recovery-{device_id}-{sequence}"
    data["device_id"] = device_id
    data["publisher_session_id"] = session_id
    data["source_sequence"] = sequence
    data["source_timestamp"] = f"2026-08-16T12:00:{sequence:02d}Z"
    data["priority"] = priority

    message = parse_telemetry_message(data)
    return store_message(connection, message, "telemetry/sensor-001")


def make_retry_wait(connection, row_id):
    mark_recovery_in_flight(connection, row_id, expected_state="pending")
    mark_retry_wait(connection, row_id)


def state_for(connection, row_id):
    return connection.execute(
        """
        SELECT
            delivery_state,
            attempt_count
        FROM outbox_messages
        WHERE id = ?
        """,
        (row_id,),
    ).fetchone()


def test_stability_time_is_required_before_recovery():
    clock = FakeClock()
    client = FakeMqttClient(connected=True)

    stable = wait_for_link_stability(
        client,
        stability_seconds=5.0,
        poll_interval_seconds=1.0,
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    assert stable is True
    assert clock.now >= 5.0


def test_health_probe_requires_qos1_acknowledgement():
    client = FakeMqttClient([FakeMessageInfo(mid=10, published=True)])

    result = publish_health_probe(client, topic="gateway/health", qos=1)

    assert result is True
    assert client.publications == [
        {
            "topic": "gateway/health",
            "payload": '{"status":"probe"}',
            "qos": 1,
            "retain": False,
        }
    ]


def test_recovery_selects_pending_and_retry_wait_in_stream_order(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        first = add_message(connection, sequence=1)
        second = add_message(connection, sequence=2)
        make_retry_wait(connection, second.row_id)

        selected = get_next_recovery_message(connection)

        assert selected is not None
        assert selected.row_id == first.row_id
        assert selected.delivery_state == "pending"

        mark_recovery_in_flight(connection,first.row_id, expected_state="pending")
        mark_broker_acknowledged(connection, first.row_id)

        selected = get_next_recovery_message(connection)

        assert selected is not None
        assert selected.row_id == second.row_id
        assert selected.delivery_state == "retry_wait"

    finally:
        connection.close()


def test_recovery_batch_is_limited(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        for sequence in range(1, 8):
            add_message(connection, sequence=sequence)

        client = FakeMqttClient(
            [
                FakeMessageInfo(mid=sequence, published=True)
                for sequence in range(1, 4)
            ]
        )

        result = publish_recovery_batch(connection, client, batch_size=3)

        assert result.attempted == 3
        assert result.acknowledged == 3
        assert result.stopped_on_failure is False
        assert result.backlog_empty is False

        acknowledged = connection.execute(
            """
            SELECT COUNT(*)
            FROM outbox_messages
            WHERE delivery_state = 'broker_acknowledged'
            """
        ).fetchone()[0]

        assert acknowledged == 3

    finally:
        connection.close()


def test_publication_failure_stops_current_batch(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        first = add_message(connection, sequence=1)
        second = add_message(connection, sequence=2)
        third = add_message(connection, sequence=3)

        client = FakeMqttClient(
            [
                FakeMessageInfo(mid=1, published=True),
                FakeMessageInfo(rc=mqtt.MQTT_ERR_NO_CONN, mid=2, published=False),
                FakeMessageInfo(mid=3,published=True),
            ]
        )

        result = publish_recovery_batch(connection, client, batch_size=3)

        assert result.attempted == 2
        assert result.acknowledged == 1
        assert result.stopped_on_failure is True

        assert (
            state_for(connection, first.row_id)["delivery_state"]
            == "broker_acknowledged"
        )
        assert state_for(connection, second.row_id)["delivery_state"] == "retry_wait"
        assert state_for(connection, third.row_id)["delivery_state"] == "pending"

        assert len(client.publications) == 2

    finally:
        connection.close()


def test_recovery_can_resume_after_failure(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        first = add_message(connection, sequence=1)
        second = add_message(connection, sequence=2)

        failing_client = FakeMqttClient(
            [
                FakeMessageInfo(rc=mqtt.MQTT_ERR_NO_CONN, mid=1, published=False)
            ]
        )

        first_result = publish_recovery_batch(connection, failing_client, batch_size=2)

        assert first_result.stopped_on_failure is True
        assert state_for(connection, first.row_id)["delivery_state"] == "retry_wait"

        recovered_client = FakeMqttClient(
            [
                FakeMessageInfo(mid=2, published=True),
                FakeMessageInfo(mid=3, published=True),
            ]
        )

        second_result = publish_recovery_batch(
            connection,
            recovered_client,
            batch_size=2,
        )

        assert second_result.attempted == 2
        assert second_result.acknowledged == 2
        assert second_result.backlog_empty is True

        first_state = state_for(connection, first.row_id)
        second_state = state_for(connection, second.row_id)

        assert first_state["delivery_state"] == "broker_acknowledged"
        assert first_state["attempt_count"] == 2

        assert second_state["delivery_state"] == "broker_acknowledged"
        assert second_state["attempt_count"] == 1

    finally:
        connection.close()


def test_limited_priority_slot_does_not_break_device_order(tmp_path):
    database_path = tmp_path / "gateway.db"
    connection = open_database(database_path, SCHEMA_PATH)

    try:
        old = add_message(
            connection,
            sequence=1,
            device_id="sensor-old",
            priority=0,
        )
        add_message(
            connection,
            sequence=1,
            device_id="sensor-priority",
            priority=5,
        )
        blocked_high = add_message(
            connection,
            sequence=2,
            device_id="sensor-old",
            priority=10,
        )
        normal = get_next_recovery_message(connection, prefer_priority=False)
        priority = get_next_recovery_message(connection, prefer_priority=True)

        assert normal is not None
        assert normal.row_id == old.row_id

        assert priority is not None
        assert priority.device_id == "sensor-priority"
        assert priority.row_id != blocked_high.row_id

    finally:
        connection.close()
