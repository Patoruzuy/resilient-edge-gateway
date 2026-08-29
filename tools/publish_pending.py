"""
Publish one pending gateway message to the upstream broker.

Stale in_flight records are first moved to retry_wait so that an
interrupted publication attempt does not remain stranded after restart.
The retry_wait records are not replayed by this tool.
"""
from datetime import datetime, timedelta, timezone
import logging
import argparse

from src.config import UpstreamConfig, configure_logging
from src.database import open_database
from src.repository import recover_stale_in_flight
from src.upstream import UpstreamMqttConnection, publish_one_pending

log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish one pending gateway message to the upstream broker."
    )
    return parser.parse_args()

def stale_before_timestamp(timeout_seconds: float) -> str:
    """Return the UTC threshold used to identify stale attempts."""
    if timeout_seconds <= 0:
        raise ValueError("stale_inflight_timeout_seconds must be positive")

    threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    return threshold.isoformat(timespec="microseconds").replace("+00:00", "Z")

def main() -> None:
    parse_args()
    configure_logging()
    config = UpstreamConfig()

    connection = open_database(
        database_path=config.database_path,
        schema_path=config.schema_path,
    )
    upstream = UpstreamMqttConnection(config)

    try:
        stale_before = stale_before_timestamp(config.stale_inflight_timeout_seconds)
        recovered = recover_stale_in_flight(connection, stale_before=stale_before)

        if recovered:
            log.info(
                "Recovered stale in_flight records: "
                "count=%s stale_before=%s",
                recovered,
                stale_before,
            )

        upstream.connect()
        result = publish_one_pending(
            connection,
            upstream.client,
            qos=config.qos,
            acknowledgement_timeout_seconds=config.acknowledgement_timeout_seconds,
        )

        log.info(
            "Baseline publication result: outcome=%s "
            "row_id=%s message_id=%s mid=%s detail=%s",
            result.outcome.value,
            result.row_id,
            result.message_id,
            result.mqtt_mid,
            result.detail,
        )

    finally:
        upstream.close()
        connection.close()


if __name__ == "__main__":
    main()
