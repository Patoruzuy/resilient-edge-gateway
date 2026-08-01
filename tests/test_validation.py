import pytest

from edge_gateway.validation import (
    MessageValidationError,
    calculate_payload_hash,
    parse_telemetry_message,
)


def valid_message() -> dict:
    return {
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
    }


def test_valid_message_is_normalised():
    message = parse_telemetry_message(valid_message())

    assert message.source_timestamp == "2026-07-15T11:00:00.000000Z"
    assert message.idempotency_key == (
        "sensor-001",
        "session-001",
        1,
    )


def test_missing_field_is_rejected():
    raw = valid_message()
    del raw["device_id"]

    with pytest.raises(MessageValidationError) as error:
        parse_telemetry_message(raw)

    assert error.value.code == "missing_fields"


def test_equivalent_payloads_have_same_hash():
    first = {"temperature_c": 18.5, "humidity_percent": 71}
    second = {"humidity_percent": 71, "temperature_c": 18.5}

    assert calculate_payload_hash(first) == calculate_payload_hash(second)
