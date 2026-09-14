# Raspberry Pi Evaluation

This folder contains the setup notes and evidence used to evaluate the resilient edge gateway on the Raspberry Pi.

## Evaluation setup

The important separation is:

The local broker runs on:

```text
localhost:1883
```

The upstream broker runs on the Windows PC:

```text
<WINDOWS_IP>:1883
```

Network impairment was only applied to the Raspberry Pi `wlan0` upstream path using Linux `tc` and NetEm. The local MQTT ingestion at `localhost:1883` was not impacted.

## Main tools

The evaluation used:

| Tool | Purpose |
|---|---|
| `python -m src` | Starts the gateway ingestion process and saves the telemetry. |
| `tools/run_evaluation.py` | Prepares a single clean evaluation run |
| `tools/simulated_publisher.py` | Generates a standard message set and creates `publisher_output.csv` |
| `tools/run_collector.py` | Captures upstream observations |
| `tools/evaluation_evidence.py` | Records events, storage samples, and additional metrics |
| `tools/netem_control.sh` | Applies, displays, and removes NetEm impairment |
| `tools/run_controlled_recovery.py` | Conducts backlog recovery |
| `tools/reconcile_run.py` | Synchronizes evidence for the publisher, gateway, and collector |

## Scenarios used for evaluation

This scenarios are used for the evaluation:

| ID | Purpose |
|----|---|
| DIRECT-BASE | Direct reference from publisher to upstream for EO1. |
| GATEWAY-BASE | Final reference for the gateway under baseline conditions. |
| DEG-100MS-10LOSS | Gateway performance with 100 ms delay and 10% packet loss. |
| OUT-15S-2HZ | A short outage that created 30 messages, followed by recovery. |
| OUT-30S-5HZ | A longer outage resulting in a backlog of 150 messages for EO3. |

Each scenario was repeated three times.

## Evidence

Each run is saved under:

RUN_ID is the scenario's ID, for example, `OUT-30S-5HZ-r1`.

```text
evidence/<RUN_ID>/
```

Depending on the scenario, the folder may have the following files:

```text
publisher_output.csv
gateway.db
evaluation.db
summary.json
reconciliation.csv
timeline.csv
recovery_metrics.json
storage_samples.csv
```

Failed, preflight, and unusual runs are kept as proof for the project but are not used from the final analysis.

Check `evidence/README.md` for more details about the dataset.
