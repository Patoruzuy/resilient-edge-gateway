"""
Upstream publication for the local-first edge gateway.

The module selects one durable pending outbox record, changes it to
in_flight, publishes it to the upstream broker at QoS 1 and stores the
resulting durable state.
"""
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

import paho.mqtt.client as mqtt

from src.config import UpstreamConfig
from src.repository import (
    PendingOutboxMessage,
    get_next_pending_message,
    mark_broker_acknowledged,
    mark_in_flight,
    mark_retry_wait,
)


log = logging.getLogger(__name__)


class PublicationOutcome(str, Enum):
    """Possible outcomes from one baseline publication attempt."""

    NO_PENDING = "no_pending"
    BROKER_ACKNOWLEDGED = "broker_acknowledged"
    RETRY_WAIT = "retry_wait"


@dataclass(frozen=True, slots=True)
class PublicationResult:
    """Result of attempting to publish one durable outbox record."""

    outcome: PublicationOutcome
    row_id: int | None = None
    message_id: str | None = None
    mqtt_mid: int | None = None
    detail: str | None = None


def publish_one_pending(
    connection: sqlite3.Connection,
    client: Any,
    *,
    qos: int = 1,
    acknowledgement_timeout_seconds: float = 5.0,
) -> PublicationResult:
    """
    Publish one pending message to the upstream broker.

    A message is marked in_flight before the MQTT publication begins.
    A completed QoS 1 exchange changes it to broker_acknowledged.
    Immediate failure, timeout or uncertain completion moves it to
    retry_wait.
    """
    pending = get_next_pending_message(connection)

    if pending is None:
        log.info("No pending outbox messages are available.")

        return PublicationResult(
            outcome=PublicationOutcome.NO_PENDING,
        )

    # Persist the beginning of the attempt before invoking the network
    # client. This makes the attempt visible after the interruption.
    mark_in_flight(connection, pending.row_id)

    try:
        message_info = client.publish(
            topic=pending.topic,
            payload=serialise_upstream_message(pending),
            qos=qos,
            retain=False,
        )

    except (ValueError, RuntimeError, OSError) as exc:
        mark_retry_wait(connection, pending.row_id)

        log.warning(
            "Upstream publication could not be started: "
            "row_id=%s message_id=%s error=%s",
            pending.row_id,
            pending.message_id,
            exc,
        )

        return PublicationResult(
            outcome=PublicationOutcome.RETRY_WAIT,
            row_id=pending.row_id,
            message_id=pending.message_id,
            detail=str(exc),
        )

    mqtt_mid = int(message_info.mid)

    # An immediate return-code failure means that the message was not
    # successfully queued by the MQTT client.
    if message_info.rc != mqtt.MQTT_ERR_SUCCESS:
        mark_retry_wait(connection, pending.row_id)

        detail = (
            "MQTT publish returned error code "
            f"{int(message_info.rc)}."
        )

        log.warning(
            "Upstream publication was not queued: "
            "row_id=%s message_id=%s mid=%s rc=%s",
            pending.row_id,
            pending.message_id,
            mqtt_mid,
            message_info.rc,
        )

        return PublicationResult(
            outcome=PublicationOutcome.RETRY_WAIT,
            row_id=pending.row_id,
            message_id=pending.message_id,
            mqtt_mid=mqtt_mid,
            detail=detail,
        )

    try:
        message_info.wait_for_publish(
            timeout=acknowledgement_timeout_seconds
        )

    except (ValueError, RuntimeError) as exc:
        # The broker may or may not have accepted the publication.
        # Treating the state as uncertain is consistent with the
        # at-least-once recovery problem I have described in TMA03.
        mark_retry_wait(connection, pending.row_id)

        log.warning(
            "Upstream acknowledgement was not confirmed: "
            "row_id=%s message_id=%s mid=%s error=%s",
            pending.row_id,
            pending.message_id,
            mqtt_mid,
            exc,
        )

        return PublicationResult(
            outcome=PublicationOutcome.RETRY_WAIT,
            row_id=pending.row_id,
            message_id=pending.message_id,
            mqtt_mid=mqtt_mid,
            detail=str(exc),
        )

    if not message_info.is_published():
        mark_retry_wait(connection, pending.row_id)

        detail = (
            "QoS 1 acknowledgement was not confirmed before timeout."
        )

        log.warning(
            "Upstream acknowledgement timed out: "
            "row_id=%s message_id=%s mid=%s",
            pending.row_id,
            pending.message_id,
            mqtt_mid,
        )

        return PublicationResult(
            outcome=PublicationOutcome.RETRY_WAIT,
            row_id=pending.row_id,
            message_id=pending.message_id,
            mqtt_mid=mqtt_mid,
            detail=detail,
        )

    mark_broker_acknowledged(
        connection,
        pending.row_id,
    )

    log.info(
        "Upstream broker acknowledged publication: "
        "row_id=%s message_id=%s mid=%s",
        pending.row_id,
        pending.message_id,
        mqtt_mid,
    )

    return PublicationResult(
        outcome=PublicationOutcome.BROKER_ACKNOWLEDGED,
        row_id=pending.row_id,
        message_id=pending.message_id,
        mqtt_mid=mqtt_mid,
    )

def serialise_upstream_message(
    pending: PendingOutboxMessage,
) -> str:
    """
    Reconstruct the telemetry message for upstream publication.

    The SQLite outbox stores message identity separately from the
    payload. Creating the envelope keeps the identity information
    that is required by the evaluation collector.
    """

    payload = json.loads(pending.payload)

    envelope = {
        "message_id": pending.message_id,
        "device_id": pending.device_id,
        "publisher_session_id": (
            pending.publisher_session_id
        ),
        "source_sequence": pending.source_sequence,
        "source_timestamp": pending.source_timestamp,
        "priority": pending.priority,
        "payload": payload,
    }

    return json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


class UpstreamMqttConnection:
    """
    Manage the MQTT connection to the upstream broker.

    The Paho network loop runs in a background thread while the main
    worker waits for the QoS 1 publication result.
    """

    def __init__(self, config: UpstreamConfig) -> None:
        self._config = config
        self._connected = threading.Event()
        self._connection_error: str | None = None
        self._loop_started = False

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
        )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    @property
    def client(self) -> mqtt.Client:
        """Return the connected Paho client used for publication."""
        return self._client

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Record whether the broker accepted the connection."""
        del client, userdata, flags, properties

        if reason_code == 0:
            self._connection_error = None
            self._connected.set()

            log.info(
                "Connected to upstream broker: host=%s port=%s",
                self._config.broker_host,
                self._config.broker_port,
            )
            return

        self._connection_error = str(reason_code)
        self._connected.set()

        log.error(
            "Upstream broker rejected connection: reason=%s",
            reason_code,
        )

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Record loss or closure of the upstream connection."""
        del client, userdata, disconnect_flags, properties

        self._connected.clear()

        if reason_code == 0:
            log.info("Disconnected from upstream broker.")
        else:
            log.warning(
                "Unexpected upstream disconnection: reason=%s",
                reason_code,
            )

    def connect(self) -> None:
        """
        Connect and wait until the broker's response has been processed.
        """
        self._connected.clear()
        self._connection_error = None

        try:
            self._client.connect(
                host=self._config.broker_host,
                port=self._config.broker_port,
                keepalive=self._config.keepalive_seconds,
            )
        except OSError as exc:
            raise RuntimeError(
                "Unable to open the upstream broker connection."
            ) from exc

        self._client.loop_start()
        self._loop_started = True

        completed = self._connected.wait(
            timeout=self._config.connect_timeout_seconds
        )

        if not completed:
            self.close()

            raise RuntimeError(
                "Timed out while waiting for the upstream "
                "broker connection."
            )

        if self._connection_error is not None:
            error = self._connection_error
            self.close()

            raise RuntimeError(
                "The upstream broker rejected the connection: "
                f"{error}"
            )

    def close(self) -> None:
        """Disconnect cleanly and stop the Paho network thread."""
        if self._client.is_connected():
            self._client.disconnect()

        if self._loop_started:
            self._client.loop_stop()
            self._loop_started = False

        self._connected.clear()
