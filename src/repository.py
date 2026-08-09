"""
Store incoming telemetry messages in the outbox table with idempotency
guarantees.

This module inserts validated TelemetryMessage objects into SQLite and ensures
each message is stored exactly once. It uses a composite idempotency key
(device_id, publisher_session_id, source_sequence) to detect duplicates, and
falls back to the globally unique message_id when the composite key does not
match.

Outcomes:
- INSERTED: a new outbox row was created.
- DUPLICATE: the same message content was already stored.
- CONFLICT: the same identity or message_id was reused with different
  payload content.

Payloads are stored as normalised JSON and hashed using SHA‑256 so that
logically identical payloads produce the same hash. Timestamps are stored
in UTC with microsecond precision.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .models import TelemetryMessage
from .validation import calculate_payload_hash, normalised_payload_json


class StoreOutcome(str, Enum):
    """Possible results when storing a telemetry message."""
    INSERTED = "inserted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class StoreResult:
    """Result of storing a message, including outcome and row details."""
    outcome: StoreOutcome
    row_id: int
    message_id: str


@dataclass(frozen=True, slots=True)
class PendingOutboxMessage:
    """Pending outbox message selected for upstream publication """
    row_id: int
    message_id: str
    topic: str
    payload: str
    source_timestamp: str
    attempt_count: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
    timespec="microseconds"
    ).replace("+00:00", "Z")


def store_message(
    connection: sqlite3.Connection,
    message: TelemetryMessage,
    topic: str) -> StoreResult:
    """
    Store a telemetry message exactly once.

    A new row is inserted unless an existing message matches the
    idempotency key or message_id. The payload hash is used to detect
    whether the stored content is identical or conflicting.

    Outcomes:
    - INSERTED: a new outbox row was committed.
    - DUPLICATE: the same message content already exists.
    - CONFLICT: the same identity or message_id refers to different content.
    """
    topic = topic.strip()

    if not topic:
        raise ValueError("topic must be a non-empty string")

    now = utc_now()
    # Detects stable hashing and duplicates.
    payload_json = normalised_payload_json(message.payload)
    payload_hash = calculate_payload_hash(message.payload)

    try:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO outbox_messages (
                    message_id,
                    device_id,
                    publisher_session_id,
                    source_sequence,
                    source_timestamp,
                    received_at,
                    topic,
                    payload,
                    payload_hash,
                    priority,
                    delivery_state,
                    attempt_count,
                    last_attempt_at,
                    acknowledged_at,
                    next_retry_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    'pending', 0, NULL, NULL, NULL, ?, ?
                )
                """,
                (
                    message.message_id,
                    message.device_id,
                    message.publisher_session_id,
                    message.source_sequence,
                    message.source_timestamp,
                    now,
                    topic,
                    payload_json,
                    payload_hash,
                    message.priority,
                    now,
                    now,
                ),
            )

        row_id = cursor.lastrowid

        if row_id is None:
            raise RuntimeError(
            "SQLite did not return the inserted outbox row ID."
            )

        return StoreResult(
            outcome=StoreOutcome.INSERTED,
            row_id=int(row_id),
            message_id=message.message_id,
        )

    except sqlite3.IntegrityError:
        # First check the composite idempotency key defined in TMA03.
        # This ensures each message is stored exactly once.
        existing = connection.execute(
            """
            SELECT id, message_id, payload_hash
            FROM outbox_messages
            WHERE device_id = ?
                AND publisher_session_id = ?
                AND source_sequence = ?
            """,
            message.idempotency_key,
        ).fetchone()

        if existing is not None:
            if str(existing["payload_hash"]) == payload_hash:
                return StoreResult(
                    outcome=StoreOutcome.DUPLICATE,
                    row_id=int(existing["id"]),
                    message_id=str(existing["message_id"]),
                )
            return StoreResult(
                outcome=StoreOutcome.CONFLICT,
                row_id=int(existing["id"]),
                message_id=str(existing["message_id"]),
            )

        # If the idempotency key did not match, check message_id instead.
        existing = connection.execute(
            """
            SELECT
                id,
                message_id,
                device_id,
                publisher_session_id,
                source_sequence,
                payload_hash
            FROM outbox_messages
            WHERE message_id = ?
            """,
            (message.message_id,),
        ).fetchone()

        if existing is None:
            # The constraint failure was not caused by either expected
            # uniqueness rule. Preserve the original database error.
            raise

        same_identity = (
            str(existing["device_id"]) == message.device_id
            and str(existing["publisher_session_id"])
            == message.publisher_session_id
            and int(existing["source_sequence"])
            == message.source_sequence
            and str(existing["payload_hash"]) == payload_hash
        )

        outcome = (
            StoreOutcome.DUPLICATE
            if same_identity
            else StoreOutcome.CONFLICT
        )

        return StoreResult(
            outcome=outcome,
            row_id=int(existing["id"]),
            message_id=str(existing["message_id"]),
        )


def get_next_pending_message(
    connection: sqlite3.Connection,
    ) -> PendingOutboxMessage | None:
    """
    Return the oldest pending message.
    The worker selects one record at a time.
    """
    row = connection.execute(
        """
        SELECT
            id,
            message_id,
            topic,
            payload,
            source_timestamp,
            attempt_count
        FROM outbox_messages
        WHERE delivery_state = "pending"
        ORDER BY source_timestamp ASC, id ASC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    return PendingOutboxMessage(
        row_id=int(row["id"]),
        message_id=str(row["message_id"]),
        topic=str(row["topic"]),
        payload=str(row["payload"]),
        source_timestamp=str(row["source_timestamp"]),
        attempt_count=int(row["attempt_count"]),
    )


def _require_single_transition(
    cursor: sqlite3.Cursor,
    row_id: int,
    expected_state: str,
    target_state: str,
    ) -> None:
    """Verify that one row completed the expected transaction."""
    if cursor.rowcount !=1:
        raise RuntimeError(
            "Unable to change outbox row "
            f"{row_id} from {expected_state!r} "
            f"to {target_state!r}."
        )


def mark_in_flight(
    connection: sqlite3.Connection,
    row_id: int,
    ) -> None:
    """
    Mark a pending message as being published upstream
    The attempt count and timestamp are commited before calling the MQTT client.
    If the process stoips afterwards, the durable in_flight row provides
    evidence of the interrupted attempt.
    """
    now = utc_now()

    with connection:
        cursor = connection.execute(
            """
            UPDATE outbox_messages
            SET
                delivery_state = 'in_flight',
                attempt_count = attempt_count + 1,
                last_attempt_at = ?,
                next_retry_at = NULL,
                updated_at = ?
            WHERE id = ?
              AND delivery_state = 'pending'
            """,
            (now, now, row_id),
        )

        _require_single_transition(
            cursor,
            row_id=row_id,
            expected_state="pending",
            target_state="in_flight",
        )


def mark_broker_acknowledged(
    connection: sqlite3.Connection,
    row_id: int,
) -> None:
    """
    Record completion of the upstream QoS 1 acknowledgement exchange.

    This state confirms broker acknowledgement. It does not prove that
    the later evaluation collector has seen the publication.
    """
    now = utc_now()

    with connection:
        cursor = connection.execute(
            """
            UPDATE outbox_messages
            SET
                delivery_state = 'broker_acknowledged',
                acknowledged_at = ?,
                next_retry_at = NULL,
                updated_at = ?
            WHERE id = ?
              AND delivery_state = 'in_flight'
            """,
            (now, now, row_id),
        )

        _require_single_transition(
            cursor,
            row_id=row_id,
            expected_state="in_flight",
            target_state="broker_acknowledged",
        )


def mark_retry_wait(
    connection: sqlite3.Connection,
    row_id: int,
) -> None:
    """Move an unsuccessful or uncertain attempt to retry_wait."""
    now = utc_now()

    with connection:
        cursor = connection.execute(
            """
            UPDATE outbox_messages
            SET
                delivery_state = 'retry_wait',
                next_retry_at = NULL,
                updated_at = ?
            WHERE id = ?
              AND delivery_state = 'in_flight'
            """,
            (now, row_id),
        )

        _require_single_transition(
            cursor,
            row_id=row_id,
            expected_state="in_flight",
            target_state="retry_wait",
        )
