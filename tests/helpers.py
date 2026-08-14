import json

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

def valid_message(payload: dict | None = None) -> dict:
    """Retunrs a valid telemetry message as dict."""
    return {
        "message_id": "msg-000001",
        "device_id": "sensor-001",
        "publisher_session_id": "session-001",
        "source_sequence": 1,
        "source_timestamp": "2026-07-15T11:00:00Z",
        "priority": 0,
        "payload": payload or {"temperature_c": 18.5},
    }

def valid_message_bytes() -> bytes:
    """Return the valid telemetry message as the MQTT-style UTF-8 bytes"""
    return json.dumps(
        valid_message(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
