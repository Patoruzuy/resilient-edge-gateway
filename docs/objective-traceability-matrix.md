# Objective traceability matrix

Created: 20/07/2026  
Last updated: 14/08/2026

This matrix links the TMA03 development and evaluation objectives to the current implementation and evidence.

| Objective | Current implementation or evidence | Status |
|---|---|---|
| DO1 | Telemetry contract, validation, UTC timestamp normalisation and local MQTT ingestion are implemented and tested. | Implemented |
| DO2 | SQLite WAL outbox, local persistence, durable delivery states and baseline upstream QoS 1 publication are implemented and tested. | Implemented |
| DO3 | Controlled recovery still requires link-stability detection, retry eligibility, bounded backlog replay and replay interruption handling. | Not started |
| DO4 | Composite idempotency key, uniqueness constraints and canonical payload-hash comparison classify expected duplicates and conflicting content. | Implemented |
| EO1 | Run-specific publisher and collector evidence can now be reconciled. Baseline run `baseline-050-001` observed 50/50 expected messages with 100.0% delivery completeness. Formal controlled-recovery trials remain outstanding. | In progress |
| EO2 | Gateway duplicate classification is implemented and the collector preserves repeated observations. Deliberate retransmission and recovery scenarios are still required. | Implemented |
| EO3 | Recovery timing fields exist, but backlog drain time has not yet been measured during controlled recovery. | Not started |
| EO4 | SQLite persistence is operational, but formal storage behaviour measurements during longer outages have not yet been collected. | Not started |
| EO5 | Linux `tc` and NetEm have been checked during exploratory work. Formal impairment-based evaluation has not yet begun. | Exploratory only |

## Status definitions

- **Not started:** the planned feature or formal evaluation has not begun.
- **In progress:** part of the implementation or measurement method exists, but the required evaluation is incomplete.
- **Exploratory only:** the method or tooling has been checked, but it has not yet been used for formal evaluation.
- **Implemented:** the feature is present and its focused tests pass.
- **Evaluated:** formal experimental evidence has been collected and analysed.
- **Complete:** implementation, evaluation and final evidence are complete where required.

## Current position

### Development objectives

DO1, DO2 and DO4 are implemented. The local-first edge gateway can validate telemetry, commit accepted messages to the SQLite WAL outbox, control duplicate insertion and publish selected records to the upstream broker.

DO3 remains the main outstanding development objective. The next recovery work must introduce link-stability checks and bounded backlog replay rather than simply draining the stored backlog after connectivity returns.

### Evaluation objectives

EO1 now has a working measurement method. During baseline run `baseline-050-001`, 50 unique messages were generated, all 50 were present in the gateway, all 50 reached `broker_acknowledged`, and all 50 were independently observed by the evaluation collector. No missing messages, duplicate observations or payload conflicts were recorded. Baseline delivery completeness was therefore 100.0%.

This baseline is not treated as evidence of resilience under intermittent connectivity. EO1 remains in progress until the same measurement approach is applied during controlled recovery and impairment-based evaluation.

EO2 is implemented. Duplicate control works and can be measured. It does not yet tell you how many duplicates controlled recovery creates under intermittent connectivity.

EO3 and EO4 depend on the controlled recovery and outage scenarios that have not yet been run. EO5 remains exploratory because NetEm has been validated as a tool, but the formal repeated impairment scenarios are still outstanding.
