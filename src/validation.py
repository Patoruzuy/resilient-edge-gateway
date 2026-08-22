"""
Validation helpers for incoming telemetry messages.

This module checks that telemetry input is well‑formed before it is turned
into a TelemetryMessage. It validates message structure, field types, and
timestamp formatting, and ensures the payload can be converted into a
normalised JSON string for hashing and duplicate detection.

The payload hash should be generated from normalised JSON,
using sorted keys and consistent separators. This avoids treating
equivalent JSON formatting as different content.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from .models import TelemetryMessage

# Required fields expected in every telemetry message.
REQUIRED_FIELDS = {
    "message_id",
    "device_id",
    "publisher_session_id",
    "source_sequence",
    "source_timestamp",
    "priority",
    "payload",
}

# I need structured error codes.
class MessageValidationError(ValueError):
    """Raised when incoming telemetry does not satisfy the message structure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _require_non_empty_string(data: Mapping[str, Any], field_name: str) -> str:
    """
    Ensure the field exists and contains a non‑empty string.
    Returns the trimmed string or raise a validation error.
    """
    value = data.get(field_name)

    if not isinstance(value, str) or not value.strip():
        raise MessageValidationError(
            "invalid_string",
            f"{field_name} must be a non-empty string",
        )
    return value.strip()


def _require_non_negative_integer(data: Mapping[str, Any], field_name: str) -> int:
    """
    Ensure the field exists and contains an integer greater than or equal to zero.
    Returns a non-negative integer or raise a validation error.
    """
    value = data.get(field_name)

    # bool is a subclass of int in python, but True and False are not valid
    # sequence numbers or priority values for this message.
    if not isinstance(value, int) or isinstance(value, bool):
        raise MessageValidationError(
            "invalid_integer",
            f"{field_name} must be an integer.",
        )

    if value < 0:
        raise MessageValidationError(
            "integer_out_of_range",
            f"{field_name} must be at least 0,",
        )
    return value


def normalise_utc_timestamp(value: Any) -> str:
    """
    Validate and normalise an ISO 8601 timestamp to UTC with microsecond precision.
    Accepts strings with a timezone or a trailing 'Z' and creates a normalised
    UTC timestamp ending in Z.
    """
    if not isinstance(value, str) or not value.strip():
        raise MessageValidationError(
            "invalid_timestamp",
            "source_timestamp must be a non-empty ISO string.",
        )

    timestamp_text = value.strip()

    try:
        # Replace trailing Z with UTC offset so fromisoformat can parse it.
        parsed = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
    except ValueError as e:
        raise MessageValidationError(
            "invalid_timestamp",
            "source_timestamp must include a timezone or Z suffix.",
        ) from e

    if parsed.tzinfo is None:
        raise MessageValidationError(
            "invalid_timezone",
            "source_timestamp muct include a timezone or Z suffix.",
        )

    # Convert to UTC representation
    normalised = parsed.astimezone(timezone.utc)

    return normalised.isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalised_payload_json(payload: Mapping[str, Any]) -> str:
    """
    Produce a normalised JSON string for the payload.

    Keys are sorted and whitespace removed so equivalent payloads always
    produce the same representation. This is used for hashing and detecting
    duplicate messages.
    """
    try:
        # Normalised JSON removes differences caused only by key order or
        # whitespace. This supports DO4 by allowing equivalent payloads to produce
        # the same SHA-256 hash during duplicate classification.
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as e:
        raise MessageValidationError(
            "invalid_payload",
            "payload must contain valid JSON values",
        ) from e


def calculate_payload_hash(payload: Mapping[str, Any]) -> str:
    """
    Produce a SHA-256 hash of the normalised paylod JSON.
    Ensures that logically identical payloads produce identical hashes.
    """
    normalised_payload = normalised_payload_json(payload)
    return hashlib.sha256(normalised_payload.encode("utf-8")).hexdigest()


def serialise_telemetry_envelope(message: Mapping[str, Any]) -> str:
    """
    Serialise a complete telemetry message for MQTT publication.
    """
    envelope = {
        "message_id": message.message_id,
        "device_id": message.device_id,
        "publisher_session_id": message.publisher_session_id,
        "source_sequence": message.source_sequence,
        "source_timestamp": message.source_timestamp,
        "priority": message.priority,
        "payload": json.loads(message.payload),
    }
    return normalised_payload_json(envelope)


def parse_telemetry_message(raw_message: bytes | str | Mapping[str, Any]) -> TelemetryMessage:
    """
    Parse and validate telemetry messages from bytes, JSON string, or mapping.
    Ensure required field exist, validates types, normalises timestamp, and
    checks that the payload is a compatible JSON.
    Returns a TelemetryMessage instance with the validated data or raise a validation error.
    """
    # Decode bytes into UTF-8 text
    if isinstance(raw_message, bytes):
        try:
            raw_message = raw_message.decode("utf-8")
        except UnicodeDecodeError as e:
            raise MessageValidationError(
                "invalid_encoding",
                "MQTT payload must use UTF-8 encoding",
            ) from e

    # Parse JSON text into a dict
    if isinstance(raw_message, str):
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError as e:
            raise MessageValidationError(
                "invalid_json",
                "MQTT payload must contain valid JSON",
            ) from e

    # Accept dict ojects.
    elif isinstance(raw_message, Mapping):
        data = dict(raw_message)

    else:
        raise MessageValidationError(
            "invalid_message_type",
            "Telemetry inout must be byte, JSON string or a mapping.",
        )

    # Root must be a JSON object
    if not isinstance(data, dict):
        raise MessageValidationError(
            "invalid_root",
            "Telemetry JSON must contain an object at its root.",
        )
    # Checks fro missing required fields
    missing_fields = sorted(REQUIRED_FIELDS - data.keys())
    if missing_fields:
        raise MessageValidationError(
            "missing_fields",
            "Missing required fields: " + ", ".join(missing_fields),
        )

    # Validate the payload structure
    payload = data["payload"]
    if not isinstance(payload, dict):
        raise MessageValidationError(
            "invalid_payload",
            "payload must be a JSON object.",
        )

    # Normalise the JSON payload
    normalised_payload_json(payload)

    # Build the validated message
    return TelemetryMessage(
        message_id=_require_non_empty_string(data, "message_id"),
        device_id=_require_non_empty_string(data, "device_id"),
        publisher_session_id=_require_non_empty_string(data, "publisher_session_id"),
        source_sequence=_require_non_negative_integer(data, "source_sequence"),
        source_timestamp=normalise_utc_timestamp(data["source_timestamp"]),
        priority=_require_non_negative_integer(data, "priority"),
        payload=dict(payload),
    )
