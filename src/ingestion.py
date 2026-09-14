"""
Local MQTT ingestion for the edge gateway.

The module subscribes to the local Mosquitto broker, validates received
telemetry and stores accepted messages to the SQLite WAL outbox.

Validation failures and database errors are logged and returned as ingestion
outcomes rather than terminating the network loop.
"""
import logging
import sqlite3
from dataclasses import dataclass
from enum import Enum

import paho.mqtt.client as mqtt

from src.config import IngestionConfig
from src.database import open_database
from src.repository import StoreOutcome, StoreResult, store_message
from src.validation import MessageValidationError, parse_telemetry_message


log = logging.getLogger(__name__)


class IngestionOutcome(str, Enum):
    """Possible outcome when processin a local MQTT publication. """
    INSERTED = "inserted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    REJECTED = "rejected"
    ERROR = "error"

@dataclass(frozen=True, slots=True)
class IngestionResult:
    """
    Result produced after processing one MQTT publication.

    Contains the mapped outcome, the topic, and optional identifiers or
    error details depending on the result.
    """
    outcome: IngestionOutcome
    topic: str
    message_id: str | None = None
    row_id: int | None = None
    reason_code: str | None = None
    detail: str | None = None

def process_mqtt_publication(
    connection: sqlite3.Connection,
    topic: str,
    payload: bytes,
    ) -> IngestionResult:
    """
    Validates and persist one MQTT publication.
    Validation errors are returned as REJECTED outcomes. Database errors
    are returned as ERROR outcomes. Successful commits produce INSERTED,
    DUPLICATE or CONFLICT outcomes depending on repository logic.
    """
    try:
        message = parse_telemetry_message(payload)
    except MessageValidationError as e:
        # Validation failures must not stop the MQTT loop.
        log.warning(
            "Telemetry publication rejected: topic=%s code=%s detail=%s",
            topic,
            e.code,
            str(e),
        )

        return IngestionResult(
            outcome=IngestionOutcome.REJECTED,
            topic=topic,
            reason_code=e.code,
            detail=str(e),
        )

    try:
        stored = store_message(
            connection=connection,
            message=message,
            topic=topic,
        )
    except sqlite3.Error as e:
        # Database failures must not stop the MQTT loop.
        log.exception(
            "SQLite error while storing telemetry: topic=%s message_id=%s",
            topic,
            message.message_id,
        )

        return IngestionResult(
            outcome=IngestionOutcome.ERROR,
            topic=topic,
            message_id=message.message_id,
            reason_code="database_error",
            detail=str(e),
        )

    return _map_store_result(topic, stored)

def _map_store_result(topic: str, result: StoreResult) -> IngestionResult:
    """
    Convert a repository StoreResult into an ingestion-level result.
    This keeps ingestion independent from repository internals and
    ensures consistent logging and outcome mapping.
    """
    outcome_mapping = {
        StoreOutcome.INSERTED: IngestionOutcome.INSERTED,
        StoreOutcome.DUPLICATE: IngestionOutcome.DUPLICATE,
        StoreOutcome.CONFLICT: IngestionOutcome.CONFLICT,
    }
    ingestion_result = IngestionResult(
        outcome=outcome_mapping[result.outcome],
        topic=topic,
        message_id=result.message_id,
        row_id=result.row_id,
    )
    log.info(
        "Telemetry publication processed: topic=%s message_id=%s"
        "row_id=%s outcome=%s",
        topic,
        result.message_id,
        result.row_id,
        ingestion_result.outcome.value,
    )

    return ingestion_result


class GatewayIngestionService:
    """
    Receive telemetry from the local broker and store it.
    The SQLite connection is opened in the same thread that runs the blocking
    MQTT netwrok loop. This avoids sharing the connection between threads during
    the current single-process implementation.
    """
    def __init__(self, config: IngestionConfig) -> None:
        self._config = config
        self._connection: sqlite3.Connection | None = None
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
        )
        # Register callbacks.
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties,
    ) -> None:
        """
        Subcribe after every successful connection.
        Establish the subscription here means that it is renewed when
        the gateway reconnects to the local broker.
        """
        # Remove unused parameters to avoid accidental use and keep the
        # callback signature clean.
        del userdata, flags, properties
        if reason_code !=0:
            log.error("connection to local broker failed: reason=%s", reason_code)
            return
        result, message_id = client.subscribe(
            self._config.topic_filter,
            qos=self._config.qos,
        )
        if result != mqtt.MQTT_ERR_SUCCESS:
            log.error(
                "Unable to subscribe to local topic: filter=%s result=%s",
                self._config.topic_filter,
                result,
            )
            return
        log.info(
            "Subscribed to local broker: filter=%s qos=%s mid=%s",
            self._config.topic_filter,
            self._config.qos,
            message_id,
        )

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        """
        Process one MQTT publication without stopping the network loop
        All exceptions are caught so that one malformed message does not
        terminate ingestion
        """
        # Same reason as above: make it explicit that these are unused.
        del client, userdata
        if self._connection is None:
            log.error("MQTT publication received before database initialisation")
            return
        try:
            process_mqtt_publication(
                connection=self._connection,
                topic=message.topic,
                payload=message.payload,
            )
        except Exception:
            # The callback boundry catches unexpected fauls so that one
            # malformed message does not stop ingestion.
            log.exception("Unexpected ingestion failure: topic=%s", message.topic)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Record disconnection from the local broker."""
        del client, userdata, disconnect_flags, properties
        log.warning("Disconnected from local broker: reason=%s", reason_code)

    def run(self) -> None:
        """Open the database, connect to Mosquitto snd process messages"""
        self._connection = open_database(
            database_path=self._config.database_path,
            schema_path=self._config.schema_path,
        )
        try:
            log.info(
                "connecting to local Mosquitto broker: host=%s port=%s",
                self._config.broker_host,
                self._config.broker_port,
            )

            self._client.connect(
                host=self._config.broker_host,
                port=self._config.broker_port,
                keepalive=self._config.keepalive_seconds,
            )

            # loop_forever() processes network traffic and dispateches the
            # registred callback in this process.
            self._client.loop_forever()

        finally:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def stop(self) -> None:
        """Requet a clean MQTT disconnection"""
        self._client.disconnect()
