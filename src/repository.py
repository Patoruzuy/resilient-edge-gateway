"""
Store incoming telemetry messages in the outbox table with idempotency
guarantees and operations for evaluation collector evidence.

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
    device_id: str
    publisher_session_id: str
    source_sequence: int
    source_timestamp: str
    priority: int
    topic: str
    payload: str
    attempt_count: int
    delivery_state: str = "pending"

@dataclass(frozen=True, slots=True)
class GatewayDuplicateSummary:
    """Duplicate-control evidence recorded by the gateway."""
    expected_retransmissions: int
    payload_conflicts: int


@dataclass(frozen=True, slots=True)
class CollectorDuplicateSummary:
    """Duplicate-control evidence calculated from observations."""
    total_observations: int
    unique_identities: int
    repeated_observations: int
    conflicting_observations: int


def utc_now() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
        ).replace("+00:00", "Z")


# Gateway outbox operations

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
            stored_payload_hash = str(existing["payload_hash"])

            if stored_payload_hash == payload_hash:
                with connection:
                    _record_duplicate_observation(
                        connection,
                        message=message,
                        classification="expected_retransmission",
                        stored_payload_hash=stored_payload_hash,
                        observed_payload_hash=payload_hash,
                    )

                return StoreResult(
                    outcome=StoreOutcome.DUPLICATE,
                    row_id=int(existing["id"]),
                    message_id=str(existing["message_id"]),
                )
            with connection:
                _record_duplicate_observation(
                    connection,
                    message=message,
                    classification="payload_conflict",
                    stored_payload_hash=stored_payload_hash,
                    observed_payload_hash=payload_hash,
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
            # uniqueness rule. Keeps the original database error.
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
        classification = (
            "expected_retransmission"
            if outcome == StoreOutcome.DUPLICATE
            else "payload_conflict"
        )

        with connection:
            _record_duplicate_observation(
                connection,
                message=message,
                classification=classification,
                stored_payload_hash=str(existing["payload_hash"]),
                observed_payload_hash=payload_hash,
            )
        return StoreResult(
            outcome=outcome,
            row_id=int(existing["id"]),
            message_id=str(existing["message_id"]),
        )

def _outbox_message_from_row(row: sqlite3.Row) -> PendingOutboxMessage:
    """Convert an outbox query result into the publication model."""
    return PendingOutboxMessage(
        row_id=int(row["id"]),
        message_id=str(row["message_id"]),
        device_id=str(row["device_id"]),
        publisher_session_id=str(row["publisher_session_id"]),
        source_sequence=int(row["source_sequence"]),
        source_timestamp=str(row["source_timestamp"]),
        priority=int(row["priority"]),
        topic=str(row["topic"]),
        payload=str(row["payload"]),
        attempt_count=int(row["attempt_count"]),
        delivery_state=str(row["delivery_state"]),
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
            device_id,
            publisher_session_id,
            source_sequence,
            source_timestamp,
            priority,
            topic,
            payload,
            attempt_count,
            delivery_state
        FROM outbox_messages
        WHERE delivery_state = "pending"
        ORDER BY source_timestamp ASC, id ASC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    return _outbox_message_from_row(row)


def get_next_recovery_message(
    connection: sqlite3.Connection,
    prefer_priority: bool = False,
) -> PendingOutboxMessage | None:
    """
    Return one message eligible for controlled recovery.
    Only pending and retry_wait records are eligible. A later source sequence
    from the same device and publisher session is not selected while an earlier
    record from that stream stays pending, retry_wait or in_flight.
    """
    row = connection.execute(
        """
        SELECT
            current.id,
            current.message_id,
            current.device_id,
            current.publisher_session_id,
            current.source_sequence,
            current.source_timestamp,
            current.priority,
            current.topic,
            current.payload,
            current.attempt_count,
            current.delivery_state
        FROM outbox_messages AS current
        WHERE current.delivery_state IN ('pending', 'retry_wait')
          AND NOT EXISTS (
              SELECT 1
              FROM outbox_messages AS earlier
              WHERE earlier.device_id = current.device_id
                AND earlier.publisher_session_id =
                    current.publisher_session_id
                AND earlier.source_sequence < current.source_sequence
                AND earlier.delivery_state IN (
                    'pending',
                    'retry_wait',
                    'in_flight'
                )
          )
        ORDER BY
            CASE WHEN ? THEN current.priority END DESC,
            current.source_timestamp ASC,
            current.id ASC
        LIMIT 1
        """,
        (1 if prefer_priority else 0,),
    ).fetchone()

    if row is None:
        return None

    return _outbox_message_from_row(row)


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

def mark_recovery_in_flight(
    connection: sqlite3.Connection,
    row_id: int,
    expected_state: str,
) -> None:
    """
    Start a controlled-recovery publication attempt.
    A recovery message may begin in pending or retry_wait. The in_flight
    transition is committed before the MQTT publication.
    """
    if expected_state not in {"pending", "retry_wait"}:
        raise ValueError(
            "controlled recovery can only publish pending or retry_wait records"
        )

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
              AND delivery_state = ?
            """,
            (now, now, row_id, expected_state),
        )

        _require_single_transition(
            cursor,
            row_id=row_id,
            expected_state=expected_state,
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

def recover_stale_in_flight(
    connection: sqlite3.Connection,
    stale_before: str,
) -> int:
    """
    Move stale in_flight publication attempts to retry_wait.
    The caller provides the stale threshold so that recovery behaviour
    remains configurable and straightforward to test. Recovery does not
    increase attempt_count because no new publication attempt is made.
    """
    now = utc_now()

    with connection:
        cursor = connection.execute(
            """
            UPDATE outbox_messages
            SET
                delivery_state = 'retry_wait',
                next_retry_at = NULL,
                updated_at = ?
            WHERE delivery_state = 'in_flight'
              AND last_attempt_at IS NOT NULL
              AND last_attempt_at <= ?
            """,
            (now, stale_before),
        )

    return max(int(cursor.rowcount), 0)

# Evaluation evidence operations

def record_collector_observation(
    connection: sqlite3.Connection,
    run_id: str,
    topic: str,
    qos: int,
    retained: bool,
    mqtt_duplicate: bool,
    raw_message: bytes,
    message: TelemetryMessage,
) -> int:
    """
    Record one collector observation.
    Repeated message identities are intentionally retained because
    duplicate observations form part of the later EO2 evaluation.
    """
    received_at = utc_now()

    with connection:
        cursor = connection.execute(
            """
            INSERT INTO collector_observations (
                run_id,
                received_at,
                topic,
                qos,
                retained,
                mqtt_duplicate,
                message_id,
                device_id,
                publisher_session_id,
                source_sequence,
                source_timestamp,
                priority,
                payload,
                payload_hash,
                raw_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                received_at,
                topic,
                qos,
                int(retained),
                int(mqtt_duplicate),
                message.message_id,
                message.device_id,
                message.publisher_session_id,
                message.source_sequence,
                message.source_timestamp,
                message.priority,
                normalised_payload_json(message.payload),
                calculate_payload_hash(message.payload),
                raw_message,
            ),
        )
    return int(cursor.lastrowid)


def record_collector_rejection(
    connection: sqlite3.Connection,
    run_id: str,
    topic: str,
    qos: int,
    retained: bool,
    mqtt_duplicate: bool,
    raw_message: bytes,
    reason_code: str,
    detail: str,
) -> int:
    """Record an upstream publication that cannot be validated."""
    received_at = utc_now()

    with connection:
        cursor = connection.execute(
            """
            INSERT INTO collector_rejections (
                run_id,
                received_at,
                topic,
                qos,
                retained,
                mqtt_duplicate,
                reason_code,
                detail,
                raw_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                received_at,
                topic,
                qos,
                int(retained),
                int(mqtt_duplicate),
                reason_code,
                detail,
                raw_message,
            ),
        )
    return int(cursor.lastrowid)


# Duplicate control

def _record_duplicate_observation(
    connection: sqlite3.Connection,
    message: TelemetryMessage,
    classification: str,
    stored_payload_hash: str,
    observed_payload_hash: str,
) -> int:
    """Record duplicate-control evidence for later evaluation."""
    observed_at = utc_now()

    cursor = connection.execute(
        """
        INSERT INTO gateway_duplicate_observations (
            observed_at,
            observed_message_id,
            device_id,
            publisher_session_id,
            source_sequence,
            classification,
            stored_payload_hash,
            observed_payload_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observed_at,
            message.message_id,
            message.device_id,
            message.publisher_session_id,
            message.source_sequence,
            classification,
            stored_payload_hash,
            observed_payload_hash,
        ),
    )
    return int(cursor.lastrowid)


def get_gateway_duplicate_summary(
    connection: sqlite3.Connection,
) -> GatewayDuplicateSummary:
    """Return persistent gateway duplicate-control counts."""
    expected_retransmissions = connection.execute(
        """
        SELECT COUNT(*)
        FROM gateway_duplicate_observations
        WHERE classification = 'expected_retransmission'
        """
    ).fetchone()[0]

    payload_conflicts = connection.execute(
        """
        SELECT COUNT(*)
        FROM gateway_duplicate_observations
        WHERE classification = 'payload_conflict'
        """
    ).fetchone()[0]

    return GatewayDuplicateSummary(
        expected_retransmissions=int(expected_retransmissions),
        payload_conflicts=int(payload_conflicts),
    )


def get_collector_duplicate_summary(
    connection: sqlite3.Connection,
    run_id: str,
) -> CollectorDuplicateSummary:
    """
    Calculate duplicate-control evidence for one collector run.
    The first occurrence of an idempotency key establishes the payload
    hash for that logical telemetry message. Later observations with the
    same hash are repeated deliveries. A different hash for the same
    identity is conflicting content.
    """
    rows = connection.execute(
        """
        SELECT
            device_id,
            publisher_session_id,
            source_sequence,
            payload_hash
        FROM collector_observations
        WHERE run_id = ?
        ORDER BY id ASC
        """,
        (run_id,),
    ).fetchall()

    first_hash_by_identity: dict[
        tuple[str, str, int],
        str,
    ] = {}

    repeated_observations = 0
    conflicting_observations = 0

    for row in rows:
        identity = (
            str(row["device_id"]),
            str(row["publisher_session_id"]),
            int(row["source_sequence"]),
        )
        payload_hash = str(row["payload_hash"])

        first_hash = first_hash_by_identity.get(identity)

        if first_hash is None:
            first_hash_by_identity[identity] = payload_hash
            continue

        if payload_hash == first_hash:
            repeated_observations += 1
        else:
            conflicting_observations += 1

    return CollectorDuplicateSummary(
        total_observations=len(rows),
        unique_identities=len(first_hash_by_identity),
        repeated_observations=repeated_observations,
        conflicting_observations=conflicting_observations,
    )
