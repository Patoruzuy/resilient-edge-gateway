"""
Generate a telemetry set for evaluation and keeps publisher
output containing the expected message identities.
"""
import argparse
import csv
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import paho.mqtt.client as mqtt

from src.repository import utc_now
from src.validation import calculate_payload_hash, normalised_payload_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--run-id", required=True)
    parser.add_argument("--count", type=int, default=50)

    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--topic", default="telemetry/sensor-001")

    parser.add_argument("--device-id", default="sensor-001")
    parser.add_argument("--session-id", default=None,)

    parser.add_argument("--interval-ms", type=int, default=20)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.count <= 0:
        raise ValueError("count must be positive")

    session_id = args.session_id or f"{args.run_id}-session-001"

    evidence_dir = Path("evidence") / args.run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    output_path = (evidence_dir / "publisher_output.csv")

    connected = threading.Event()

    client = mqtt.Client(
        callback_api_version=(mqtt.CallbackAPIVersion.VERSION2),
        client_id=f"publisher-{args.run_id}",
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        del client, userdata, flags, properties

        if reason_code == 0:
            connected.set()

    client.on_connect = on_connect
    client.connect(args.host, args.port, keepalive=60)

    client.loop_start()

    try:
        if not connected.wait(timeout=5.0):
            raise RuntimeError("Publisher could not connect to the local broker.")

        fieldnames = [
            "run_id",
            "message_id",
            "device_id",
            "publisher_session_id",
            "source_sequence",
            "source_timestamp",
            "generated_at",
            "topic",
            "payload",
            "payload_hash",
            "local_publish_confirmed",
        ]

        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)

            writer.writeheader()

            for sequence in range(1, args.count + 1):
                message_id = (f"{args.run_id}-{sequence:06d}")

                source_timestamp = utc_now()

                payload = {
                    "temperature_c": round(18.0 + ((sequence - 1) % 20) * 0.1, 1),
                    "humidity_pct": (60 + ((sequence - 1) % 10)),
                }

                message = {
                    "message_id": message_id,
                    "device_id": args.device_id,
                    "publisher_session_id": session_id,
                    "source_sequence": sequence,
                    "source_timestamp":source_timestamp,
                    "priority": 0,
                    "payload": payload,
                }

                wire_message = normalised_payload_json(message)

                info = client.publish(
                    topic=args.topic,
                    payload=wire_message,
                    qos=1,
                    retain=False,
                )

                info.wait_for_publish(timeout=5.0)

                confirmed = info.is_published()

                writer.writerow(
                    {
                        "run_id": args.run_id,
                        "message_id": message_id,
                        "device_id": args.device_id,
                        "publisher_session_id": (session_id),
                        "source_sequence": sequence,
                        "source_timestamp": (source_timestamp),
                        "generated_at": utc_now(),
                        "topic": args.topic,
                        "payload": (normalised_payload_json(payload)),
                        "payload_hash": (calculate_payload_hash(payload)),
                        "local_publish_confirmed": (int(confirmed)),
                    }
                )

                # Keeps evidence progressively if the run is interrupted.
                file.flush()

                if not confirmed:
                    raise RuntimeError("Local publication was not "
                        f"confirmed for {message_id}"
                    )

                if args.interval_ms:
                    time.sleep(
                        args.interval_ms / 1000
                    )

    finally:
        client.disconnect()
        client.loop_stop()

    print(f"Generated {args.count} messages.")
    print(f"Publisher output: {output_path}")


if __name__ == "__main__":
    main()
