"""
MQTT evaluation collector.

The collector subscribes to the upstream broker and records every
observed telemetry publication. It does not modify gateway state.
"""
import logging
import sqlite3
import paho.mqtt.client as mqtt

from src.config import CollectorConfig, EvaluationConfig
from src.database import open_evaluation_database
from src.repository import record_collector_observation, record_collector_rejection
from src.validation import MessageValidationError, parse_telemetry_message

log = logging.getLogger(__name__)


class EvaluationCollector:
    """Collect independent evidence from the upstream MQTT broker."""

    def __init__(self, config: CollectorConfig, evaluation_config: EvaluationConfig) -> None:
        self._config = config
        self._evaluation_config = evaluation_config
        self._connection: sqlite3.Connection | None = None
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ) -> None:
        """Subscribe after every successful upstream connection."""
        del userdata, flags, properties

        if reason_code != 0:
            log.error(
                "Evaluation collector connection failed: reason=%s", reason_code
                )
            return

        result, mid = client.subscribe(self._config.topic_filter, qos=self._config.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            log.error(
                "Collector subscription failed: filter=%s result=%s",
                self._config.topic_filter,
                result,
            )
            return
        log.info(
            "Evaluation collector subscribed: run_id=%s filter=%s qos=%s mid=%s",
            self._config.run_id,
            self._config.topic_filter,
            self._config.qos,
            mid,
        )

    def _on_message(
        self,
        client,
        userdata,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Record one observed upstream MQTT publication."""
        del client, userdata

        if self._connection is None:
            log.error("Collector message received before database initialisation.")
            return
        try:
            telemetry = parse_telemetry_message(message.payload)

        except MessageValidationError as exc:
            record_collector_rejection(
                self._connection,
                run_id=self._config.run_id,
                topic=message.topic,
                qos=message.qos,
                retained=message.retain,
                mqtt_duplicate=message.dup,
                raw_message=message.payload,
                reason_code=exc.code,
                detail=str(exc),
            )

            log.warning(
                "Collector rejected publication: run_id=%s topic=%s code=%s",
                self._config.run_id,
                message.topic,
                exc.code,
            )
            return

        try:
            observation_id = record_collector_observation(
                self._connection,
                run_id=self._config.run_id,
                topic=message.topic,
                qos=message.qos,
                retained=message.retain,
                mqtt_duplicate=message.dup,
                raw_message=message.payload,
                message=telemetry,
            )

        except sqlite3.Error:
            log.exception(
                "Unable to persist collector observation: run_id=%s message_id=%s",
                self._config.run_id,
                telemetry.message_id,
            )
            return

        log.info(
            "Collector observation recorded: run_id=%s observation_id=%s message_id=%s",
            self._config.run_id,
            observation_id,
            telemetry.message_id,
        )

    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ) -> None:
        """Record collector disconnection."""
        del client, userdata, disconnect_flags, properties

        if reason_code == 0:
            log.info("Evaluation collector disconnected.")
        else:
            log.warning(
                "Evaluation collector disconnected unexpectedly: reason=%s",
                reason_code,
            )

    def run(self) -> None:
        """Open evidence storage and run the MQTT collector."""
        self._connection = open_evaluation_database(
            database_path=self._evaluation_config.database_path,
            schema_path=self._evaluation_config.schema_path,
        )
        log.info(
            "Starting evaluation collector: run_id=%s host=%s port=%s",
            self._config.run_id,
            self._config.broker_host,
            self._config.broker_port,
        )
        try:
            self._client.connect(
                host=self._config.broker_host,
                port=self._config.broker_port,
                keepalive=self._config.keepalive_seconds
                )
            self._client.loop_forever()
        finally:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def stop(self) -> None:
        """Request a clean collector shutdown."""
        self._client.disconnect()
