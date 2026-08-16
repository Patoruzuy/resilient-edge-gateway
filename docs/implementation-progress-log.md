# Implementation progress log

This log records the main implementation changes, problems and evidence for the local-first edge gateway. Detailed test results are kept in the test scenario register so that this file remains concise.

## 25/07/2026

 **Branch:**
- Initial database work

 **Completed:**
- Created SQLite database initialisation for the gateway outbox.
- Enabled SQLite Write-Ahead Logging (WAL).
- Added the uniqueness constraint used by the idempotency key.

Problem:
- Duplicate inserts were not yet classified cleanly.

 **Outcome:**
- The basic local persistence structure was created, but duplicate control still needed repository-level handling.

TMA03 objectives:
- DO2
- DO4

## 01/08/2026

 **Branch:**
- `feat/baseline-message-contract`

Commit:
- `feat(contract): define telemetry message validation and hashing`

 **Completed:**
- Defined the telemetry message fields agreed in TMA03.
- Added validation for required fields, identifiers, sequence values, timestamps and payload content.
- Normalised source timestamps to Coordinated Universal Time (UTC).
- Added canonical JSON handling and SHA-256 payload hashing.
- Added tests for valid messages, missing fields, timestamp handling and equivalent payload hashes.

 **Problems and corrections:**
- Minor typing and test-data errors were found during the first test runs and corrected.

 **Outcome:**
- The telemetry contract and validation path were implemented.
- Canonical payload hashing provided the basis for later duplicate control.

 **Evidence:**
- `models.py`
- `validation.py`
- `test_validation.py`
- Passing automated tests
- Decisions D002 and D003

TMA03 objectives:
- DO1
- DO4

## 02/08/2026

 **Branch:**
- `feat/sqlite-outbox`

 **Completed:**
- Configured the gateway database to use SQLite WAL.
- Enabled foreign-key checks for each connection.
- Added execution of `schema.sql` during database initialisation.
- Aligned the `outbox_messages` schema with the repository fields.
- Implemented durable outbox insertion and duplicate/conflict classification.
- Confirmed that committed records remain available after reopening the database.

 **Problems and corrections:**
- Mixed indentation caused errors in `database.py`.
- The schema path used by tests was unreliable.
- The database initially opened without executing `schema.sql`.
- Several repository fields were missing from the first schema version.
- These issues were corrected without changing the TMA03 message model or durable delivery states.

 **Outcome:**
- Local persistence through the SQLite WAL outbox became stable and testable.
- Expected retransmissions and conflicting content could be distinguished without creating additional outbox rows.

 **Evidence:**
- `database.py`
- `repository.py`
- `schema.sql`
- Database and repository tests
- Decision D001

TMA03 objectives:
- DO2
- DO4

## 03/08/2026 to 07/08/2026

 **Branch:**
- `feat/gateway-ingestion`

Commit:
- `feat(ingestion): persist local MQTT telemetry`

 **Completed:**
- Added configuration for the local Mosquitto broker.
- Subscribed to `telemetry/#` using MQTT Quality of Service (QoS) 1.
- Connected the MQTT callback to message validation and SQLite persistence.
- Kept validation and database logic outside the MQTT callback.
- Added outcomes for inserted, duplicate, conflict and rejected messages.
- Completed automated tests and a real local Mosquitto smoke test.

 **Problems and corrections:**
- Some result fields were initially required even when a rejected message had no row or message identifier.
- One test helper returned bytes that were not valid JSON.
- The result model and test data were corrected.

 **Outcome:**
- The local ingestion path became operational:

  `publisher → local broker → local-first edge gateway → SQLite WAL`

- This demonstrated local persistence before any upstream publication was attempted.

 **Evidence:**
- Passing ingestion tests
- Gateway smoke-test log
- SQLite row inspection
- Decision D005

TMA03 objectives:
- DO1
- DO2
- DO4

## 08/08/2026 to 09/08/2026

 **Branch:**
- `feat/upstream-publication`

 **Completed:**
- Added a separate MQTT client for publication to the upstream broker.
- Selected one eligible `pending` record at a time to avoid introducing uncontrolled backlog replay before the controlled recovery slice.
- Added the durable transitions:
  - `pending → in_flight`
  - `in_flight → broker_acknowledged`
  - `in_flight → retry_wait`
- Recorded publication attempts and acknowledgement timestamps.
- Added handling for an empty pending outbox.
- Added automated tests for success, immediate publication failure, acknowledgement timeout and no pending record.
- Verified that the full telemetry identity is preserved during upstream publication.
- Completed a real Mosquitto smoke test on `localhost:1884`.

 **Problems and corrections:**
- A SQL syntax error prevented the first upstream tests from reaching MQTT publication.
- `mark_in_flight()` used the wrong timestamp variable name.
- The empty-outbox path did not initially handle `fetchone()` returning `None`.
- The standalone publication script required correction to the project execution/import setup.
- `broker_port` was initially stored as a string instead of an integer.
- Each issue was corrected and the affected tests were rerun.

 **Outcome:**
- The gateway can now move a durably stored message to the upstream broker using QoS 1.
- Broker acknowledgement is stored as `broker_acknowledged`.
- Failed or uncertain publication remains durably available as `retry_wait`.
- This is a prerequisite for controlled recovery, but DO3 is not yet implemented.

 **Evidence:**
- `src/upstream.py`
- Updated `src/repository.py`
- `tools/publish_pending.py`
- `tests/test_upstream.py`
- Mosquitto broker and gateway logs
- SQLite state inspection
- Decision D006

TMA03 objectives:
- DO2
- Prerequisite for DO3
- Foundation for EO1 and EO2

## 09/08/2026 to 14/08/2026

 **Branch:**
- `feat/evaluation-collector`

 **Completed:**
- Added an independent MQTT evaluation collector connected to the upstream broker.
- Kept evaluation evidence in `data/evaluation.db`, separate from gateway operational state in `data/gateway.db`.
- Reused the existing Python database and repository modules to avoid unnecessary file duplication.
- Added evaluation run identifiers, receipt timestamps, message identity, payload hashes and MQTT metadata.
- Preserved repeated collector observations so that later duplicate-control evaluation can count them.
- Added persistent records for rejected collector messages.
- Confirmed that the upstream publication preserves the complete telemetry envelope required for reconciliation.
- Added shared test helpers to reduce repeated test data.
- Completed a one-message publisher-to-collector smoke test.
- Completed known-set baseline run `baseline-050-001` using 50 unique messages.
- Produced a publisher output and reconciled publisher, gateway and collector evidence.
- Calculated baseline delivery completeness from unique expected identities.

 **Problems and corrections:**
- The first repeated-observation test referenced a missing test helper.
- Collector persistence initially expected `payload_hash` to be part of `TelemetryMessage`, although the project treats it as derived evidence.
- The collector was changed to calculate the hash using the existing canonical payload-hash function.
- Raw MQTT evidence was stored as bytes rather than a Python dictionary.

Baseline evidence for `baseline-050-001`:
- Unique generated messages: 50
- Gateway records present: 50
- Gateway records `broker_acknowledged`: 50
- Collector observations: 50
- Unique expected messages observed: 50
- Missing gateway records: 0
- Missing collector observations: 0
- Duplicate collector observations: 0
- Payload conflicts: 0
- Unexpected collector identities: 0
- Baseline delivery completeness: 100.0%

 **Outcome:**
- The baseline publisher-to-collector measurement path is complete under normal, unimpaired local network conditions.
- Broker acknowledgement and collector observation are kept as separate evidence.
- Publisher, gateway and collector records can now be reconciled using telemetry identity and payload hash.
- The 100.0% result is a baseline only. It does not demonstrate resilience under intermittent connectivity.

 **Evidence:**
- `evidence/baseline-050-001/publisher_output.csv`
- `evidence/baseline-050-001/reconciliation.csv`
- `evidence/baseline-050-001/summary.json`
- `gateway.db`
- `evaluation.db`
- Mosquitto broker, gateway and collector logs
- Passing automated test suite
- Decision D007

Limitations:
- Formal duplicate-control evaluation has not yet been completed.
- Stale `in_flight` recovery remains outstanding.
- Link-stability detection and bounded backlog replay remain outstanding.
- Formal impairment-based evaluation under intermittent connectivity has not yet begun.

 **Next:**
- Complete and merge `feat/evaluation-collector`.
- Begin `feat/duplicate-control`.
- Use the existing publisher and collector evidence to measure expected retransmissions, conflicting content and collector-side duplicate arrival.

TMA03 objectives:
- EO1: measurement method implemented; formal controlled-recovery evaluation remains outstanding.
- EO2: measurement foundation implemented; deliberate duplicate scenarios remain outstanding.
- Supports later DO3 recovery evaluation.


## 14/08/2026

 **Branch:**
- `feat/duplicate-control`

 **Completed:**
- Added persistent evidence for expected retransmissions and conflicting content.
- Kept the existing idempotency key, payload hash and SQLite uniqueness constraint.
- Confirmed that repeated or conflicting messages do not create another outbox row.
- Added collector-side duplicate and conflict counts.
- Completed automated and manual duplicate-control tests.

 **Problems and corrections:**
- The initial collector duplicate test successfully stored the
  upstream observation, but the reconciliation tool failed because it
  assumed that every evaluation run has a publisher manifest.
- The reconciliation run was written for complete publisher-to-collector
  evaluation runs. DUP-03 publishes directly to the upstream broker to isolate
  collector duplicate behaviour, so no publisher manifest exists for this test.
- Added an agrument collector-only mode. This allows collector duplicate
  evidence to be analysed without the publisher-manifest requirement.

 **Evidence:**
- DUP-01 to DUP-04
- `gateway_duplicate_observations`
- collector run evidence
- D008

 **Outcome:**
- Duplicate control can now be measured at the gateway and evaluation collector.
- DO4 remains implemented and EO2 remains in progress.
- Collector duplicate observations can be analysed independently.

 **Next:**
- `feat/stale-inflight-recovery`


## 16/08/2026

**Branch:**
`feat/stale-inflight-recovery`

**Completed:**
- Added a configurable timeout for identifying stale `in_flight` records.
- Added repository recovery that moves stale records to `retry_wait`.
- Recovery does not increase `attempt_count` because no new publication attempt is made.
- Recent `in_flight` records remain unchanged.
- `pending`, `retry_wait` and `broker_acknowledged` records are unaffected.
- Added stale recovery when the baseline upstream publication tool starts.
- Kept `retry_wait` replay outside this slice so that it can be handled by controlled recovery.
- Added automated tests for stale records, recent attempts, unaffected states and recovery after database reopening.
- Completed a manual recovery smoke test using the real gateway database.

**Problems and corrections:**
- REC-01: Passed
- REC-02: Passed
- REC-03: Passed
- REC-04: Passed
- REC-05 manual test: Passed
- Complete automated test suite: Passed

**Evidence:**
- `stale-smoke-001` was stored as `pending`.
- The interrupted state was simulated as `in_flight` with one publication attempt.
- After restart, one stale `in_flight` record was detected.
- The record moved to `retry_wait`.
- `attempt_count` remained 1.
- `acknowledged_at` remained unset.
- The baseline publisher did not replay the recovered record and instead selected another `pending` message.

**Outcome:**
- An interrupted durable publication attempt no longer remains permanently stranded in `in_flight`.
- Local persistence now supports recovery to a durable retry state after restart.
- The recovered message is not automatically replayed, preserving the boundary between stale recovery and controlled recovery.
- DO3 is in progress. Link-stability detection and bounded backlog replay remain outstanding.

**Next:**
- Begin `feat/controlled-recovery`.
