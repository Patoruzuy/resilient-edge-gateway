"""
Reconcile the publisher, gateway and collector evidence for one run.
"""
import argparse
import csv
import json
import sys
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--run-id", required=True)

    parser.add_argument("--gateway-db", type=Path, default=Path("data/gateway.db"))
    parser.add_argument("--evaluation-db", type=Path, default=Path("data/evaluation.db"))

    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence"))
    parser.add_argument("--collector-only", action="store_true",
        help=("Reconcile collector duplicate-control evidence without need for "
              "publisher or gateway evidence.",
        ))

    return parser.parse_args()

def stable_key(row) -> tuple[str, str, int]:
    return (
        str(row["device_id"]),
        str(row["publisher_session_id"]),
        int(row["source_sequence"]),
    )

def read_publisher_output(path: Path) -> list[dict[str, str]]:
    with path.open(newline="",encoding="utf-8") as file:
        return list(csv.DictReader(file))

def write_csv(path: Path, rows, fieldnames,) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def main() -> None:
    args = parse_args()
    run_dir = (args.evidence_dir / args.run_id)

    publisher_rows = []

    if not args.collector_only:
        publisher_path = run_dir / "publisher_output.csv"
        publisher_rows = read_publisher_output(publisher_path)

    expected = {
        stable_key(row): row
        for row in publisher_rows
    }

    if len(expected) != len(publisher_rows):
        raise RuntimeError("Publisher output contains duplicate stable identities.")

    gateway = sqlite3.connect(args.gateway_db)
    gateway.row_factory = sqlite3.Row

    evaluation = sqlite3.connect(args.evaluation_db)
    evaluation.row_factory = sqlite3.Row

    try:
        gateway_rows = gateway.execute(
            """
            SELECT
                id,
                message_id,
                device_id,
                publisher_session_id,
                source_sequence,
                source_timestamp,
                payload_hash,
                delivery_state,
                attempt_count,
                acknowledged_at
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
        gateway.close()
        evaluation.close()

    gateway_by_key = {
        stable_key(row): row
        for row in gateway_rows
        if stable_key(row) in expected
    }
    # filter the gateway duplicate evidence
    run_gateway_duplicates = [
        row
        for row in gateway_duplicate_rows
        if stable_key(row) in expected
    ]

    collector_by_key = defaultdict(list)

    for row in collector_rows:
        collector_by_key[stable_key(row)].append(row)

    reconciliation = []
    collector_unique_matches = 0
    collector_duplicate_observations = 0
    payload_conflicts = 0
    missing_gateway = 0
    missing_collector = 0
    collector_duplicate_observations = 0
    collector_conflicting_identities = 0
    collector_conflicting_observations = 0

    for key, publisher in expected.items():
        gateway_row = gateway_by_key.get(key)
        observations = collector_by_key.get(key, [])

        expected_message_id = (publisher["message_id"])
        expected_hash = (publisher["payload_hash"])

        if gateway_row is None:
            missing_gateway += 1

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
        valid_duplicate_count = max(0, len(valid_observations) - 1)
        # Each invalid observation is a conflict
        conflict_count = len(conflicting_observations)

        collector_duplicate_observations += valid_duplicate_count
        collector_conflicting_observations += conflict_count

        if conflict_count:
            collector_conflicting_identities += 1

        reconciliation.append(
            {
                "device_id": key[0],
                "publisher_session_id": key[1],
                "source_sequence": key[2],
                "message_id": expected_message_id,
                "publisher_payload_hash": expected_hash,
                "gateway_present": int(gateway_row is not None),
                "gateway_state": (gateway_row["delivery_state"]
                    if gateway_row else ""
                ),
                "gateway_attempt_count": (gateway_row["attempt_count"]
                    if gateway_row else ""
                ),
                "collector_observation_count": len(observations),
                "collector_valid_match": int(collector_observed),
                "collector_valid_duplicate_count": valid_duplicate_count,
                "collector_duplicate_count": (duplicate_count),
                "payload_conflict": int(conflict),
            }
        )

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
    gateway_broker_acknowledged = sum(
        1
        for row in gateway_by_key.values()
        if row["delivery_state"]
        == "broker_acknowledged"
    )
    gateway_expected_retransmissions = sum(
        1
        for row in run_gateway_duplicates
        if row["classification"]
        == "expected_retransmission"
    )
    gateway_payload_conflicts = sum(
        1
        for row in run_gateway_duplicates
        if row["classification"]
        == "payload_conflict"
    )
    summary = {
        "run_id": args.run_id,
        "generated_unique": generated_unique,
        "gateway_present": len(gateway_by_key),
        "gateway_broker_acknowledged": gateway_broker_acknowledged,
        "gateway_expected_retransmissions": gateway_expected_retransmissions,
        "gateway_payload_conflicts": gateway_payload_conflicts,

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
    if not args.collector_only:
        write_csv(
            run_dir / "reconciliation.csv",
            reconciliation,
            list(reconciliation[0].keys())
            if reconciliation
            else [],
        )
        with (run_dir / "summary.json").open("w", encoding="utf-8") as file:
            json.dump(summary, file, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
