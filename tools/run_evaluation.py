"""
Prepare one formal evaluation run.
This is a helper to keep the evaluation setup repeatable without trying to automate
the complete experiment. It can create fresh databases, initialise the
evidence directory and print the publisher command for thee scenarios.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from src.database import open_database, open_evaluation_database
from src.config import EvaluationConfig, UpstreamConfig


def parse_args(upstream_config: UpstreamConfig) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare one TM470 evaluation run.")

    parser.add_argument("--scenario", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument(
        "--upstream-host",
        default=upstream_config.broker_host,
        help="The upstream broker host for the evaluation run, for example 'localhost'."
        )
    parser.add_argument("--upstream-port", type=int, default=upstream_config.broker_port)
    parser.add_argument(
        "--interface",
        required=True,
        help="The network interface used for the evaluation run, for example 'eth0'."
        )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete and recreate the evaluation databases.",
    )

    return parser.parse_args()

def load_scenario(path: Path, scenario_id: str) -> dict:
    """Read one scenario from the evaluation scenario file."""
    data = json.loads(path.read_text(encoding="utf-8"))

    for scenario in data["scenarios"]:
        if scenario["id"] == scenario_id:
            return scenario
    raise ValueError(f"Unknown scenario: {scenario_id}")

def delete_database(path: Path) -> None:
    """Remove a SQLite database and its WAL files."""
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            candidate.unlink()

def create_gateway_database(upstream_config: UpstreamConfig) -> None:
    """Create the normal gateway database from schema.sql."""
    connection = open_database(upstream_config.database_path, upstream_config.schema_path)
    connection.close()

def create_evaluation_database(evaluation_config: EvaluationConfig) -> None:
    """Create the independent collector database."""
    connection = open_evaluation_database(evaluation_config.database_path, evaluation_config.schema_path)
    connection.close()

def prepare_databases(
        scenario: dict,
        fresh: bool,
        upstream_config: UpstreamConfig,
        evaluation_config: EvaluationConfig,
    ) -> None:
    """Create the databases required by the selected scenario."""
    if fresh:
        delete_database(upstream_config.database_path)
        delete_database(evaluation_config.database_path)
    if scenario["path"] == "gateway":
        if not upstream_config.database_path.exists():
            create_gateway_database(upstream_config)
    if not evaluation_config.database_path.exists():
        create_evaluation_database(evaluation_config)


def initialise_evidence(args: argparse.Namespace) -> None:
    """Use the existing evidence tool to initialise the run."""
    command = [
        sys.executable,
        "-m",
        "tools/evaluation_evidence.py",
        "init",
        "--run-id", str(args.run_id),
        "--scenario", str(args.scenario),
        "--repeat-number", str(args.repeat),
        "--interface", str(args.interface),
        "--upstream-host", str(args.upstream_host),
    ]
    subprocess.run(command, check=True)


def print_next_steps(
        args: argparse.Namespace,
        scenario: dict,
        upstream_config: UpstreamConfig,
        evaluation_config: EvaluationConfig,
    ) -> None:
    """Print the small set of commands needed to continue the run."""
    interval_ms = round(1000 / float(scenario["rate_hz"]))
    if scenario["path"] == "direct":
        publisher_host = args.upstream_host
        publisher_port = args.upstream_port
    else:
        publisher_host = "localhost"
        publisher_port = 1883

    print()
    print("Evaluation run prepared")
    print("-----------------------")
    print(f"Run ID:   {args.run_id}")
    print(f"Scenario: {args.scenario}")
    print(f"Path:     {scenario['path']}")
    print(f"Messages: {scenario['message_count']}")
    print(f"Rate:     {scenario['rate_hz']} msg/s")
    print(f"Evidence: {evaluation_config.evidence_dir / args.run_id}")
    print()

    if scenario["path"] == "gateway":
        print(f"Gateway database: {upstream_config.database_path}")
    else:
        print("Gateway is bypassed for this direct baseline.")

    print(f"Evaluation database: {evaluation_config.database_path}")
    print()
    print("Start the collector using this run ID.")
    print("Publisher command:")
    print(
        f"{sys.executable} -m tools/simulated_publisher.py "
        f"--run-id {args.run_id} "
        f"--count {scenario['message_count']} "
        f"--interval-ms {interval_ms} "
        f"--host {publisher_host} "
        f"--port {publisher_port}"
    )
    print()

    if scenario["path"] == "direct":
        print("Reconcile with:")
        print(f"{sys.executable} -m tools/reconcile_run.py --run-id {args.run_id} --direct")
    else:
        print("Continue with the gateway, impairment and recovery")
        print("Reconcile with:")
        print(f"{sys.executable} -m tools/reconcile_run.py --run-id {args.run_id}")


def main() -> None:
    upstream_config = UpstreamConfig()
    evaluation_config = EvaluationConfig()

    args = parse_args(upstream_config)
    scenario = load_scenario(evaluation_config.scenarios_path, args.scenario)
    prepare_databases(scenario,args.fresh, upstream_config, evaluation_config)
    initialise_evidence(args)
    print_next_steps(args,scenario, upstream_config, evaluation_config)

if __name__ == "__main__":
    main()
