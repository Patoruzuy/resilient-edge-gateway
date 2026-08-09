"""
Publish one pending gateway message to the upstream broker.
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import UpstreamConfig
from src.database import open_database
from src.upstream import (
    UpstreamMqttConnection,
    publish_one_pending,
)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ),
    )

    config = UpstreamConfig()

    connection = open_database(
        database_path=config.database_path,
        schema_path=config.schema_path,
    )

    upstream = UpstreamMqttConnection(config)

    try:
        upstream.connect()

        result = publish_one_pending(
            connection,
            upstream.client,
            qos=config.qos,
            acknowledgement_timeout_seconds=(
                config.acknowledgement_timeout_seconds
            ),
        )

        logging.getLogger(__name__).info(
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
