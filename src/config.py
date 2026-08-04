"""
Configuration models for the local-first edge gateway.

This module defines the settings required for the ingestion slice of the
gateway. These settings control the local MQTT connection, subscription
filter, and the paths used for durable SQLite storage. Upstream
publication and recovery settings will be introduced in later slices.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class IngestionConfig:
    """
    Configuration for the local MQTT ingestion service.

    These settings define how the gateway connects to the local mosquitto
    broker and where incoming telemetry is stored.
    """

    broker_host: str = "localhost"
    broker_port: int = 1883 # Standard MQTT port
    topic_filter: str = "telemetry/#" # Subscribe to all telemetry topics
    qos: int = 1 # QoS 1 for the local subscription and at-least-once delivery
    client_id: str = "edge-gateway-ingestion"
    keepalive_seconds: int = 60 # Broker ping interval

    database_path: Path = Path("data/gateway.db") # The local storage
    schema_path: Path = Path("schema.sql") # SQL file schema

    # __post_init__ is called automatically after the dataclass insance is created
    def __post_init__(self) -> None:
        """Check the values assigned to fields meet the criteria"""
        if not self.broker_host.strip():
            raise ValueError("broker_host must not be empty")

        if not 1 <= self.broker_port <= 65535:
            raise ValueError("broker_port must be between 1 and 65535")

        if not self.topic_filter.strip():
            raise ValueError("topic_filter must not be empty.")

        if self.qos not in [0, 1, 2]:
            raise ValueError("qos must be 0, 1 0r 2.")

        if not self.client_id.strip():
            raise ValueError("client_id must not be empty.")

        if self.keepalive_seconds <=0:
            raise ValueError("keepalive_seconds must be positive.")
