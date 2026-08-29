"""
Run the independent upstream evaluation collector.
"""
import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import CollectorConfig, EvaluationConfig, UpstreamConfig
from src.collector import EvaluationCollector

evaluation_config = EvaluationConfig()
collector_config = UpstreamConfig()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect upstream MQTT telemetry as independent evaluation evidence.")
    )
    parser.add_argument("--run-id", required=True, help="Identifier for this evaluation run.")
    parser.add_argument("--host", default=collector_config.broker_host)
    parser.add_argument("--port", type=int, default=collector_config.broker_port)
    parser.add_argument("--topic", default=collector_config.topic_filter)
    parser.add_argument("--database", type=Path, default=evaluation_config.database_path)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format=("%(asctime)s %(levelname)s %(name)s %(message)s"),
    )
    config = CollectorConfig(
        run_id=args.run_id,
        broker_host=args.host,
        broker_port=args.port,
        topic_filter=args.topic,
    )
    collector = EvaluationCollector(config, database_path=args.database)

    try:
        collector.run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Evaluation collector stopped by user.")
        collector.stop()

if __name__ == "__main__":
    main()
