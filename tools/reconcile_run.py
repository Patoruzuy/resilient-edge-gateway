"""
Reconcile the publisher, gateway and collector evidence for one run.
To test and create evidence I created three different modes to use the tool.
Normal mode compares publisher, gateway and collector evidence.
--direct compares publisher and collector evidence only.
--collector-only prints collector duplicate evidence only.
"""
import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from src.config import EvaluationConfig, UpstreamConfig

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--run-id", required=True)

    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--direct", action="store_true",
        help="Publisher and collector evidence for a direct-publication.")
    modes.add_argument("--collector-only", action="store_true",
        help="Print collector duplicate-control evidence only")
    parser.add_argument("--gateway-db", type=Path, default=None, help="Optional gateway database path.")
    parser.add_argument("--evaluation-db", type=Path, default=None, help="Optional evaluation database path.")
    return parser.parse_args()

def stable_key(row) -> tuple[str, str, int]:
    """Return the stable telemetry identity used by the evaluation."""
    return (
        str(row["device_id"]),
        str(row["publisher_session_id"]),
        int(row["source_sequence"]),
    )

def read_publisher_output(path: Path) -> list[dict[str, str]]:
    """Read the publisher expected set."""
    if not path.is_file():
        raise FileNotFoundError(f"Publisher output does not exist: {path}")
    with path.open(newline="",encoding="utf-8") as file:
        return list(csv.DictReader(file))

def write_csv(path: Path, rows: list[dict]) -> None:
    """Write rows CSV."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        filename = list(rows[0].keys())
        writer = csv.DictWriter(file, fieldnames=filename)
        writer.writeheader()
        writer.writerows(rows)

def connect_existing_database(path: Path) -> sqlite3.Connection:
    """Open an existing SQLite database without creating antoher one."""
    if not path.is_file():
        raise FileNotFoundError(f"Database does not exist: {path}")

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection

def print_collector_duplicate_summary(collector_rows, run_id: str) -> None:
    """ Prints the collector duplicates summary without
        a publisher manifest. Only when collector_only mode is used"""
    # Group collector observations by stable telemetry key
    collector_by_key = defaultdict(list)
    for row in collector_rows:
        collector_by_key[stable_key(row)].append(row)

    duplicate_observations = 0
    conflicting_observations = 0
    conflicting_identities = 0

    for observations in collector_by_key.values():
        reference_hash = observations[0]["payload_hash"]
        has_conflict = False

        for observation in observations[1:]:
            if observation["payload_hash"] == reference_hash:
                duplicate_observations += 1
            else:
                conflicting_observations += 1
                has_conflict = True

        if has_conflict:
            conflicting_identities += 1

    summary = {
        "run_id": run_id,
        "collector_observations": len(collector_rows),
        "collector_unique_identities": len(collector_by_key),
        "collector_duplicate_observations": duplicate_observations,
        "collector_conflicting_observations": conflicting_observations,
        "collector_conflicting_identities": conflicting_identities,
    }

    print(json.dumps(summary, indent=2))

def main() -> None:
    args = parse_args()
    upstream_config = UpstreamConfig()
    evaluation_config = EvaluationConfig()

    evidence_dir = evaluation_config.evidence_dir
    gateway_db_path = (
        args.gateway_db
        if args.gateway_db is not None
        else upstream_config.database_path
    )

    evaluation_db_path = (
        args.evaluation_db
        if args.evaluation_db is not None
        else evaluation_config.database_path
    )

    evaluation = connect_existing_database(evaluation_db_path)

    try:
        collector_rows = evaluation.execute(
            """
            SELECT
                id,
                run_id,
                received_at,
                message_id,
                device_id,
                publisher_session_id,
                source_sequence,
                source_timestamp,
                payload_hash,
                mqtt_duplicate
            FROM collector_observations
            WHERE run_id = ?
            ORDER BY id
            """,
            (args.run_id,),
        ).fetchall()

    finally:
        evaluation.close()

    if args.collector_only:
        print_collector_duplicate_summary(collector_rows, args.run_id)
        return

    run_dir = (evidence_dir / args.run_id)
    publisher_path = run_dir / "publisher_output.csv"
    publisher_rows = read_publisher_output(publisher_path)

    expected = {
        stable_key(row): row
        for row in publisher_rows
    }

    if len(expected) != len(publisher_rows):
        raise RuntimeError("Publisher output contains duplicate stable identities.")

    collector_by_key = defaultdict(list)

    for row in collector_rows:
        collector_by_key[stable_key(row)].append(row)

    gateway_by_key = {}
    run_gateway_duplicates = []

    if not args.direct:
        gateway = connect_existing_database(gateway_db_path)

        try:
            gateway_rows = gateway.execute(
                """
                SELECT
                    message_id,
                    device_id,
                    publisher_session_id,
                    source_sequence,
                    delivery_state,
                    attempt_count
                FROM outbox_messages
                """
            ).fetchall()

            gateway_duplicate_rows = gateway.execute(
                """
                SELECT
                    device_id,
                    publisher_session_id,
                    source_sequence,
                    classification
                FROM gateway_duplicate_observations
                """
            ).fetchall()
        finally:
            gateway.close()

        gateway_by_key = {
            stable_key(row): row
            for row in gateway_rows
            if stable_key(row) in expected
        }
        # filter the gateway duplicate evidence
        for row in gateway_duplicate_rows:
            if stable_key(row) in expected:
                run_gateway_duplicates.append(row)

    reconciliation = []
    collector_unique_matches = 0
    collector_duplicate_observations = 0
    collector_conflicting_observations = 0
    collector_conflicting_identities = 0
    missing_collector = 0
    missing_gateway = 0

    for key, publisher in expected.items():
        observations = collector_by_key.get(key, [])
        expected_message_id = (publisher["message_id"])
        expected_hash = (publisher["payload_hash"])

        valid_observations = [
            observation
            for observation in observations
            if (
                observation["message_id"] == expected_message_id
                and observation["payload_hash"] == expected_hash
            )
        ]
        conflicting_observations = [
            observation
            for observation in observations
            if (
                observation["message_id"] != expected_message_id
                or observation["payload_hash"] != expected_hash
            )
        ]

        collector_observed = bool(valid_observations)

        if collector_observed:
            collector_unique_matches += 1
        else:
            missing_collector += 1


        # Only the repeated valid copies count as normal duplicates
        duplicate_count = max(0, len(valid_observations) - 1)
        # Each invalid observation is a conflict
        conflict_count = len(conflicting_observations)

        collector_duplicate_observations += duplicate_count
        collector_conflicting_observations += conflict_count

        if conflict_count:
            collector_conflicting_identities += 1

        row = {
            "device_id": key[0],
            "publisher_session_id": key[1],
            "source_sequence": key[2],
            "message_id": expected_message_id,
            "publisher_payload_hash": expected_hash,
            "collector_observation_count": len(observations),
            "collector_valid_match": int(collector_observed),
            "collector_valid_duplicate_count": duplicate_count,
            "collector_conflict_count": conflict_count,
        }

        if not args.direct:
            gateway_row = gateway_by_key.get(key)

            if gateway_row is None:
                missing_gateway += 1

            row.update(
                {
                    "gateway_present": int(gateway_row is not None),
                    "gateway_state": (
                        gateway_row["delivery_state"]
                        if gateway_row
                        else ""
                    ),
                    "gateway_attempt_count": (
                        gateway_row["attempt_count"]
                        if gateway_row
                        else ""
                    ),
                }
            )

        reconciliation.append(row)

    generated_unique = len(expected)
    delivery_completeness = (
        100.0
        * collector_unique_matches
        / generated_unique
        if generated_unique
        else 0.0
    )
    unexpected_collector = sum(
        1
        for key in collector_by_key
        if key not in expected
    )

    summary = {
        "run_id": args.run_id,
        "evaluation_db": str(evaluation_db_path),
        "generated_unique": generated_unique,

        "collector_observations": len(collector_rows),
        "collector_unique_expected_observed": collector_unique_matches,
        "collector_duplicate_observations": collector_duplicate_observations,
        "collector_conflicting_observations": collector_conflicting_observations,
        "collector_conflicting_identities": collector_conflicting_identities,

        "missing_gateway": missing_gateway,
        "missing_collector": missing_collector,
        "unexpected_collector_identities": unexpected_collector,
        "delivery_completeness_pct": round(delivery_completeness, 3),
    }

    if not args.direct:
        gateway_broker_acknowledged = sum(
            1
            for row in gateway_by_key.values()
            if row["delivery_state"] == "broker_acknowledged"
        )
        gateway_expected_retransmissions = sum(
            1
            for row in run_gateway_duplicates
            if row["classification"] == "expected_retransmission"
        )
        gateway_payload_conflicts = sum(
            1
            for row in run_gateway_duplicates
            if row["classification"] == "payload_conflict"
        )
        summary.update(
            {   
                "gateway_db": str(gateway_db_path),
                "gateway_present": len(gateway_by_key),
                "gateway_broker_acknowledged": gateway_broker_acknowledged,
                "gateway_expected_retransmissions": gateway_expected_retransmissions,
                "gateway_payload_conflicts": gateway_payload_conflicts,
                "missing_gateway": missing_gateway,
            }
        )

    write_csv(run_dir / "reconciliation.csv", reconciliation)
    with (run_dir / "summary.json").open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
