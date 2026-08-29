"""
Executable for the local gateway ingestion service.
"""
import logging

from src.config import IngestionConfig, configure_logging
from src.ingestion import GatewayIngestionService


def main() -> None:
    configure_logging()

    config = IngestionConfig()
    service = GatewayIngestionService(config)

    try:
        service.run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Gateway ingestion stopped by user.")
        service.stop()


if __name__ == "__main__":
    main()
