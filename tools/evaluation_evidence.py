"""
Record light evidence for one impairment evaluation run.

It records the impairment parameters, experiment
timeline and SQLite storage samples needed for EO3, EO4 and EO5.
"""
import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import EvaluationConfig, UpstreamConfig
from src.repository import utc_now

TIMELINE_FIELDS = ("timestamp", "event", "detail")
STORAGE_FIELDS = (
    "timestamp",
    "sample_point",
    "pending",
    "in_flight",
    "retry_wait",
    "broker_acknowledged",
    "attempt_count_total",
    "database_bytes",
    "wal_bytes",
    "total_bytes",
)


def parse_utc(value: str) -> datetime:
    """Parse a UTC timestamp written by this tool."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def append_csv(path: Path, fieldnames, row: dict[str, object]) -> None:
    """Append one CSV row, creating the header when necessary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()

    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

def file_size(path: Path) -> int:
    """Return a file size, or zero if the file is absent."""
    if path.exists():
        return path.stat().st_size
    return 0

def read_csv(path: Path) -> list[dict[str, str]]:
    """Read CSV rows when the file exists."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

def is_run_dir(dir) -> Path:
    """Refuse commands against an uninitialised evidence directory."""
    run_dir = Path(dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Not an initialised evaluation run: {run_dir}")
    return run_dir

def load_scenario(scenario_id: str, scenarios_path: Path) -> dict:
    """ Return one scenario from evaluation/scenarios.json."""
    if not scenarios_path.is_file():
        raise FileNotFoundError(f"Scenario file does not exist: {scenarios_path}")

    data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    scenario_rows = data.get("scenarios")

    for scenario in scenario_rows:
        if scenario["id"] == scenario_id:
            return scenario
    raise ValueError(f"Unknown scenario: {scenario_id}")

def recovery_snapshot(config: UpstreamConfig) -> dict:
    """Returns the controlled-recovery settings."""

    return {
        "link_stability_seconds": config.link_stability_seconds,
        "replay_batch_size": config.replay_batch_size,
        "replay_batch_pause_seconds": config.replay_batch_pause_seconds,
        "health_topic": config.health_topic,
    }

def initialise_run(args: argparse.Namespace) -> None:
    """Create the evidence directory and record planned parameters."""
    evaluation_config = EvaluationConfig()
    config = UpstreamConfig()
    scenario = load_scenario(args.scenario, evaluation_config.scenarios_path)
    run_dir = evaluation_config.evidence_dir / args.run_id

    run_dir.mkdir(parents=True,exist_ok=False)

    impairment = {
        "run_id": args.run_id,
        "scenario": args.scenario,
        "repeat_number": args.repeat_number,
        "created_at": utc_now(),
        "path": scenario["path"],
        "interface": args.interface,
        "upstream_host": args.upstream_host,
        "message_count": int(scenario["message_count"]),
        "message_rate_hz": float(scenario["rate_hz"]),
        "delay_ms": float(scenario["delay_ms"]),
        "loss_pct": float(scenario["loss_pct"]),
        "configured_outage_seconds": float(scenario["outage_seconds"]),
        "recovery": recovery_snapshot(config),
    }

    (run_dir / "impairment.json").write_text(
        json.dumps(impairment, indent=2) + "\n", encoding="utf-8",
    )

    print(run_dir)


def record_event(args: argparse.Namespace) -> None:
    """Record one experiment event with an independent UTC timestamp."""
    run_dir = is_run_dir(args.run_dir)
    timeline_path = run_dir / "timeline.csv"

    append_csv(
        timeline_path, TIMELINE_FIELDS,
        {"timestamp": utc_now(),"event": args.event, "detail": args.detail or ""},
    )


def storage_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Read durable outbox counts needed for storage evidence."""
    result = {
        "pending": 0,
        "in_flight": 0,
        "retry_wait": 0,
        "broker_acknowledged": 0,
    }

    rows = connection.execute(
        """
        SELECT delivery_state, COUNT(*) AS count
        FROM outbox_messages
        GROUP BY delivery_state
        """
    ).fetchall()

    for state, count in rows:
        if state in result:
            result[str(state)] = int(count)
    return result

def sample_storage(args: argparse.Namespace) -> None:
    """Append one storage and durable-state sample."""
    run_dir = is_run_dir(args.run_dir)
    evidence_config = EvaluationConfig()
    impairment = json.loads((run_dir / "impairment.json").read_text(encoding="utf-8"))

    if impairment["path"] != "gateway":
        raise ValueError("Storage sampling is only used for gateway scenarios.")

    database_path = evidence_config.database_path
    if not database_path.is_file():
        raise FileNotFoundError(f"Gateway database does not exist: {database_path}")
    # Opens the existing SQLite database without creating or changing it.
    database_uri = f"file:{database_path.resolve()}?mode=ro"

    connection = sqlite3.connect(database_uri, uri=True)
    try:
        counts = storage_counts(connection)
        attempt_count_total = int(
            connection.execute(
                """
                SELECT COALESCE(SUM(attempt_count), 0)
                FROM outbox_messages
                """
            ).fetchone()[0]
        )
    finally:
        connection.close()

    wal_path = Path(f"{database_path}-wal")

    database_bytes = file_size(database_path)
    wal_bytes = file_size(wal_path)

    append_csv(
        run_dir / "storage_samples.csv",
        STORAGE_FIELDS,
        {
            "timestamp": utc_now(),
            "sample_point": args.sample_point,
            **counts,
            "attempt_count_total": attempt_count_total,
            "database_bytes": database_bytes,
            "wal_bytes": wal_bytes,
            "total_bytes": (database_bytes + wal_bytes),
        },
    )

def first_event(timeline: list[dict[str, str]], event_name: str) -> str | None:
    """Return the first matching event timestamp."""
    matches = []
    for row in timeline:
        if row["event"] == event_name:
            matches.append(row["timestamp"])
    if len(matches) > 1:
        raise RuntimeError(f"Event recorded more than once: {event_name}")

    return matches[0] if matches else None

def finalise_run(args: argparse.Namespace) -> None:
    """Calculate EO3 and EO4 helper metrics from recorded evidence."""
    run_dir = is_run_dir(args.run_dir)
    impairment = json.loads((run_dir / "impairment.json").read_text(encoding="utf-8"))
    timeline = read_csv(run_dir / "timeline.csv")
    storage = read_csv(run_dir / "storage_samples.csv")

    total_sizes = []
    backlog_sizes = []

    impairment_applied = first_event(timeline, "impairment_applied")
    impairment_removed = first_event(timeline, "impairment_removed")
    recovery_started = first_event(timeline,"recovery_started")
    recovery_complete = first_event(timeline, "recovery_complete")

    actual_outage_seconds = None
    if impairment_applied and impairment_removed:
        actual_outage_seconds = (
            parse_utc(impairment_removed) - parse_utc(impairment_applied)
        ).total_seconds()

    backlog_drain_seconds = None

    if recovery_started and recovery_complete:
        backlog_drain_seconds = (
            parse_utc(recovery_complete) - parse_utc(recovery_started)
        ).total_seconds()

    for row in storage:
        if row.get("total_bytes"):
            total_sizes.append(int(row["total_bytes"]))

    for row in storage:
        backlog_sizes.append(
        int(row["pending"])
        + int(row["in_flight"])
        + int(row["retry_wait"])
        )

    metrics = {
        "generated_at": utc_now(),
        "configured_outage_seconds": impairment.get("configured_outage_seconds"),
        "actual_outage_seconds": actual_outage_seconds,
        "backlog_drain_seconds": backlog_drain_seconds,
        "storage_growth_bytes": (total_sizes[-1] - total_sizes[0]
            if len(total_sizes) >= 2 else None
        ),
        "max_eligible_backlog": (max(backlog_sizes) if backlog_sizes else None),
        "timeline_events": len(timeline),
        "storage_samples": len(storage),
    }

    (run_dir / "recovery_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8",
    )

    print(json.dumps(metrics, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Record evidence for impairment-based evaluation.")
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--run-id", required=True)
    init_parser.add_argument("--scenario", required=True)
    init_parser.add_argument("--repeat-number", type=int, required=True)
    init_parser.add_argument("--interface", required=True)
    init_parser.add_argument("--upstream-host", required=True)
    init_parser.set_defaults(func=initialise_run)

    event_parser = subparsers.add_parser("event")
    event_parser.add_argument("--run-dir", required=True)
    event_parser.add_argument("--event", required=True)
    event_parser.add_argument("--detail")
    event_parser.set_defaults(func=record_event)

    storage_parser = subparsers.add_parser("storage")
    storage_parser.add_argument("--run-dir", required=True)
    storage_parser.add_argument("--sample-point", required=True)
    storage_parser.set_defaults(func=sample_storage)

    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("--run-dir", required=True)
    finish_parser.set_defaults(func=finalise_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
