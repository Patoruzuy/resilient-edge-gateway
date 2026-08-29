"""
Run the independent upstream evaluation collector.
"""
import argparse
import logging
from pathlib import Path

from src.config import CollectorConfig, EvaluationConfig, configure_logging
from src.collector import EvaluationCollector


def parse_args() -> argparse.Namespace:
    evaluation_config = EvaluationConfig()
    parser = argparse.ArgumentParser(
        description=(
            "Collect upstream MQTT telemetry as independent evaluation evidence.")
    )
    parser.add_argument("--run-id", required=True, help="Identifier for this evaluation run.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--topic", default="telemetry/#")
    parser.add_argument("--database", type=Path, default=evaluation_config.database_path)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    config = CollectorConfig(
        run_id=args.run_id,
        broker_host=args.host,
        broker_port=args.port,
        topic_filter=args.topic,
    )

    evaluation_config = EvaluationConfig(database_path=args.database)
    collector = EvaluationCollector(config, evaluation_config)

    try:
        collector.run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Evaluation collector stopped by user.")
        collector.stop()

if __name__ == "__main__":
    main()
