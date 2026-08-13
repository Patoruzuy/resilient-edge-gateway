"""
Configuration models for the local-first edge gateway.

This module defines the settings required for the ingestion and upstream of the
gateway. These settings control the local MQTT connection, subscription
filter, and the paths used for durable SQLite storage.

Port 1884 is suitable when the local and upstream brokers are being
simulated on the same computer. However, we need to change it to the second host
and port used by the actual test environment.
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


@dataclass(frozen=True, slots=True)
class UpstreamConfig:
    """
    Configuration for publication to the upstream broker.
    This configuration supports one record at a time publication.
    """
    broker_host: str = "localhost"
    broker_port: str = 1884 # Standard MQTT port
    client_id: str = "edge-gateway-upstream"
    qos: int = 1 # QoS 1 for the local subscription and at-least-once delivery
    keepalive_seconds: int = 60 # Broker ping interval

    connect_timeout_seconds: float = 5.0
    acknowledgement_timeout_seconds: float = 5.0

    database_path: Path = Path("data/gateway.db") # The local storage
    schema_path: Path = Path("schema.sql") # SQL file schema

    # __post_init__ is called automatically after the dataclass insance is created
    def __post_init__(self) -> None:
        """Check the values assigned to fields meet the criteria"""
        if not self.broker_host.strip():
            raise ValueError("broker_host must not be empty")
        if not 1 <= self.broker_port <= 65535:
            raise ValueError("broker_port must be between 1 and 65535")
        # The project evaluates acknowledgement uncertainty using QoS 1.
        if self.qos != 1:
            raise ValueError("The upstream publisher must use QoS 1.")
        if not self.client_id.strip():
            raise ValueError("client_id must not be empty.")
        if self.keepalive_seconds <=0:
            raise ValueError("keepalive_seconds must be positive.")
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive.")
        if self.acknowledgement_timeout_seconds <= 0:
            raise ValueError("acknowledgement_timeout_seconds must be positive.")


@dataclass(frozen=True, slots=True)
class CollectorConfig:
    """Configuration for the independent evaluation collector."""
    run_id: str
    broker_host: str = "localhost"
    broker_port: int = 1883 # Standard MQTT port
    topic_filter: str = "telemetry/#" # Subscribe to all telemetry topics
    qos: int = 1 # QoS 1 for the local subscription and at-least-once delivery

    client_id: str = "edge-gateway-evaluation-collector"
    keepalive_seconds: int = 60 # Broker ping interval
    database_path: Path = Path("data/evaluation.db") # The local storage
    schema_path: Path = Path("evaluation_schema.sql") # SQL file schema

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty.")
        if not self.broker_host.strip():
            raise ValueError("broker_host must not be empty.")
        if not 1 <= self.broker_port <= 65535:
            raise ValueError("broker_port must be between 1 and 65535.")
        if not self.topic_filter.strip():
            raise ValueError("topic_filter must not be empty.")
        if self.qos != 1:
            raise ValueError("The evaluation collector must use QoS 1.")
        if not self.client_id.strip():
            raise ValueError("client_id must not be empty.")
