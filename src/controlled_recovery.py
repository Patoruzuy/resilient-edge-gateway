"""
Controlled backlog recovery for the local-first edge gateway.

Recovery waits until a stable upstream connection, confirms the path with
a QoS 1 health publication, then sends out a limited batch of pending or
retry_wait telemetry. If the publication fails or is not sure, the current
batch is halted, allowing recovery to continue once the path is stable again.
"""
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

import paho.mqtt.client as mqtt

from .repository import (
    PendingOutboxMessage,
    get_next_recovery_message,
    mark_broker_acknowledged,
    mark_recovery_in_flight,
    mark_retry_wait,
)
from src.validation import serialise_telemetry_envelope

log = logging.getLogger(__name__)

PRIORITY_SLOT_INTERVAL = 5


class RecoveryPublicationOutcome(str, Enum):
    """Outcome of one controlled-recovery publication attempt."""
    BROKER_ACKNOWLEDGED = "broker_acknowledged"
    RETRY_WAIT = "retry_wait"


@dataclass(frozen=True, slots=True)
class RecoveryPublicationResult:
    """Result of one controlled-recovery publication."""
    outcome: RecoveryPublicationOutcome
    row_id: int
    message_id: str
    mqtt_mid: int | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RecoveryBatchResult:
    """Result of one bounded recovery batch."""
    attempted: int
    acknowledged: int
    stopped_on_failure: bool
    backlog_empty: bool


def wait_for_link_stability(
    client,
    stability_seconds: float,
    poll_interval_seconds: float = 0.1,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bool:
    """
    Require the MQTT connection to stay always available.
    If the connection drops before the stability period completes, the
    stability check fails and must start again later.
    """
    if stability_seconds < 0:
        raise ValueError("stability_seconds cannot be negative")

    if not client.is_connected():
        return False

    stable_since = monotonic_fn()

    while monotonic_fn() - stable_since < stability_seconds:
        if not client.is_connected():
            return False

        remaining = stability_seconds - (monotonic_fn() - stable_since)
        sleep_fn(min(poll_interval_seconds, max(remaining, 0.0)))

    return client.is_connected()


def publish_health_probe(
    client,
    topic: str,
    qos: int = 1,
    acknowledgement_timeout_seconds: float = 5.0,
) -> bool:
    """
    Confirm that the upstream broker can acknowledge a QoS 1 publication.
    """
    info = client.publish(
        topic=topic,
        payload='{"status":"probe"}',
        qos=qos,
        retain=False,
    )

    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        return False

    try:
        info.wait_for_publish(timeout=acknowledgement_timeout_seconds)
    except (RuntimeError, ValueError):
        return False

    return bool(info.is_published())


def publish_recovery_message(
    connection: sqlite3.Connection,
    client,
    message: PendingOutboxMessage,
    qos: int = 1,
    acknowledgement_timeout_seconds: float = 5.0,
) -> RecoveryPublicationResult:
    """Publish one selected recovery message using state changes."""
    mark_recovery_in_flight(
        connection,
        message.row_id,
        expected_state=message.delivery_state,
    )

    info = client.publish(
        topic=message.topic,
        payload=serialise_telemetry_envelope(message),
        qos=qos,
        retain=False,
    )

    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        mark_retry_wait(connection, message.row_id)
        return RecoveryPublicationResult(
            outcome=RecoveryPublicationOutcome.RETRY_WAIT,
            row_id=message.row_id,
            message_id=message.message_id,
            mqtt_mid=getattr(info, "mid", None),
            detail=f"mqtt publish returned rc={info.rc}",
        )

    try:
        info.wait_for_publish(timeout=acknowledgement_timeout_seconds)
    except (RuntimeError, ValueError) as e:
        mark_retry_wait(connection, message.row_id)
        return RecoveryPublicationResult(
            outcome=RecoveryPublicationOutcome.RETRY_WAIT,
            row_id=message.row_id,
            message_id=message.message_id,
            mqtt_mid=getattr(info, "mid", None),
            detail=str(e),
        )

    if not info.is_published():
        mark_retry_wait(connection, message.row_id)
        return RecoveryPublicationResult(
            outcome=RecoveryPublicationOutcome.RETRY_WAIT,
            row_id=message.row_id,
            message_id=message.message_id,
            mqtt_mid=getattr(info, "mid", None),
            detail="broker acknowledgement was not confirmed",
        )

    mark_broker_acknowledged(connection, message.row_id)

    return RecoveryPublicationResult(
        outcome=RecoveryPublicationOutcome.BROKER_ACKNOWLEDGED,
        row_id=message.row_id,
        message_id=message.message_id,
        mqtt_mid=getattr(info, "mid", None),
    )


def publish_recovery_batch(
    connection: sqlite3.Connection,
    client,
    batch_size: int,
    qos: int = 1,
    acknowledgement_timeout_seconds: float = 5.0,
) -> RecoveryBatchResult:
    """
    A single limited batch should be released at any given time.
    Four selections prioritize the oldest eligible stream head.
    Every fifth selection is designated as a limited priority slot.
    This approach allows for some prioritization without permitting newer
    high-priority traffic to entirely obstruct the processing of
    older backlog records.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    attempted = 0
    acknowledged = 0

    for position in range(1, batch_size + 1):
        prefer_priority = position % PRIORITY_SLOT_INTERVAL == 0

        message = get_next_recovery_message(
            connection,
            prefer_priority=prefer_priority,
        )

        if message is None:
            return RecoveryBatchResult(
                attempted=attempted,
                acknowledged=acknowledged,
                stopped_on_failure=False,
                backlog_empty=True,
            )

        result = publish_recovery_message(
            connection,
            client,
            message,
            qos=qos,
            acknowledgement_timeout_seconds=acknowledgement_timeout_seconds,
        )
        attempted += 1

        if result.outcome == RecoveryPublicationOutcome.BROKER_ACKNOWLEDGED:
            acknowledged += 1
            log.info(
                "Recovery publication acknowledged: "
                "row_id=%s message_id=%s",
                result.row_id,
                result.message_id,
            )
            continue

        log.warning(
            "Controlled recovery stopped after publication failure: "
            "row_id=%s message_id=%s detail=%s",
            result.row_id,
            result.message_id,
            result.detail,
        )
        return RecoveryBatchResult(
            attempted=attempted,
            acknowledged=acknowledged,
            stopped_on_failure=True,
            backlog_empty=False,
        )

    remaining = get_next_recovery_message(connection) is None

    return RecoveryBatchResult(
        attempted=attempted,
        acknowledged=acknowledged,
        stopped_on_failure=False,
        backlog_empty=remaining,
    )
