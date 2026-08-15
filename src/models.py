"""
This module is the telemetry structure.

- message identifier
- device identifier
- publisher session identifier
- source sequence number
- source timestamp
- priority
- payload

The MQTT topic remains outside the JSON message because it arrives through
the MQTT envelope and is passed separately to the repository.
"""

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class TelemetryMessage:
    """Validated and normalised technical telemetry message."""
    message_id: str
    device_id: str
    publisher_session_id: str
    source_sequence: int
    source_timestamp: str
    priority: int
    payload: dict[str, Any]

    @property
    def idempotency_key(self) -> tuple[str, str, int]:
        return(
            self.device_id,
            self.publisher_session_id,
            self.source_sequence,
        )
