"""
Run controlled recovery of the durable MQTT backlog.

The tool waits for a stable upstream connection, checks the path using
a QoS 1 health publication, then drains eligible records in bounded
batches. If connectivity fails, the stability check starts again before
another batch is attempted.
"""
from datetime import datetime, timedelta, timezone
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import UpstreamConfig
from src.controlled_recovery import (
    publish_health_probe,
    publish_recovery_batch,
    wait_for_link_stability,
)
from src.database import open_database
from src.repository import recover_stale_in_flight
from src.upstream import UpstreamMqttConnection

log = logging.getLogger(__name__)


def stale_before_timestamp(timeout_seconds: float) -> str:
    """Return the UTC threshold used to identify stale attempts."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    return threshold.isoformat(timespec="microseconds").replace("+00:00", "Z")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = UpstreamConfig()
    connection = open_database(
        database_path=config.database_path,
        schema_path=config.schema_path,
    )
    upstream = UpstreamMqttConnection(config)

    try:
        recovered = recover_stale_in_flight(
            connection,
            stale_before=stale_before_timestamp(
                config.stale_inflight_timeout_seconds
            ),
        )
        if recovered:
            log.info("Recovered stale in_flight records: count=%s", recovered)

        upstream.connect()
        while True:
            # A full stability time is required when controlled
            # recovery starts or after a previous failure made the
            # upstream path doubtful.
            if not wait_for_link_stability(
                upstream.client,
                stability_seconds=config.link_stability_seconds,
            ):
                log.info("Upstream path is not stable; waiting before recovery.")
                time.sleep(1.0)
                continue
            # Confirm the path using a QoS 1 health publication
            # before starting backlog recovery
            if not publish_health_probe(
                upstream.client,
                topic=config.health_topic,
                qos=config.qos,
                acknowledgement_timeout_seconds=(
                    config.health_acknowledgement_timeout_seconds
                ),
            ):
                log.warning(
                    "Health publication was not acknowledged; "
                    "recovery will wait for a new stable time."
                )
                time.sleep(1.0)
                continue
            # Once the stability time and initial health probe pass,
            # recovery stay active across limited batches. A failed
            # publication or health probe returns execution to the outer
            # loop, where a new stability time is required.
            while True:
                result = publish_recovery_batch(
                    connection,
                    upstream.client,
                    batch_size=config.replay_batch_size,
                    qos=config.qos,
                    acknowledgement_timeout_seconds=(
                        config.acknowledgement_timeout_seconds
                    ),
                )
                log.info(
                    "Recovery batch completed: attempted=%s acknowledged=%s "
                    "stopped_on_failure=%s backlog_empty=%s",
                    result.attempted,
                    result.acknowledged,
                    result.stopped_on_failure,
                    result.backlog_empty,
                )
                if result.backlog_empty:
                    log.info("No eligible backlog remains. Controlled recovery complete.")
                    return
                # If a publication failed or became doubtful, do not
                # continue consuming the backlog. Return to the outer
                # loop so that another full stability time is required.
                if result.stopped_on_failure:
                    log.warning(
                        "Recovery batch stopped after an upstream "
                        "publication failure; returning to the stability time."
                    )
                    time.sleep(1.0)
                    break
                # A pause prevents the backlog from being released
                # as one uncontrolled burst.
                time.sleep(config.replay_batch_pause_seconds)
                # Between successful batches, use the lighter health
                # check rather than repeating the full stability delay.
                if not publish_health_probe(
                    upstream.client,
                    topic=config.health_topic,
                    qos=config.qos,
                    acknowledgement_timeout_seconds=(
                        config.health_acknowledgement_timeout_seconds
                    ),
                ):
                    log.warning(
                        "Health publication failed between recovery "
                        "batches; returning to the stability time."
                    )
                    time.sleep(1.0)
                    break
    except KeyboardInterrupt:
        log.info("Controlled recovery stopped by user.")

    finally:
        upstream.close()
        connection.close()


if __name__ == "__main__":
    main()
