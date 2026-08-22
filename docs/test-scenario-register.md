# Test scenario register

This register records the main tests used to support the TMA03 objectives. Detailed debugging history is kept in the implementation progress log.


## Database, validation and ingestion

### DB-01: Database initialisation

**Purpose:** Confirm that a fresh gateway database is created using the agreed SQLite WAL schema.

**Expected:** `schema.sql` runs, `outbox_messages` exists, WAL mode is active and schema version is 1.

**Actual:** Passed after correcting schema execution and test path handling.

**Evidence:** database tests, `database.py`, `schema.sql`.

**Objectives:** DO2


### DB-02: Persistence after reopening

**Purpose:** Confirm that a committed outbox record remains available after closing and reopening the database.

**Expected:** identity, payload and `pending` state remain unchanged.

**Actual:** Passed.

**Evidence:** database reopening test and SQLite inspection.

**Objectives:** DO2


### VAL-01: Valid telemetry message

**Purpose:** Confirm that a valid telemetry message is accepted and normalised.

**Expected:** required fields are accepted, source timestamp is normalised to UTC and canonical payload handling succeeds.

**Actual:** Passed.

**Objectives:** DO1


### VAL-02: Malformed telemetry rejection

**Purpose:** Confirm that malformed JSON or a missing required field is rejected before local persistence.

**Expected:** validation fails and no outbox row is created.

**Actual:** Passed.

**Objectives:** DO1


### ING-01: Valid local MQTT ingestion

**Purpose:** Confirm that a valid local MQTT publication is validated and committed to the SQLite WAL outbox.

**Expected:** one `pending` row is created and the MQTT topic is recorded.

**Actual:** Passed.

**Objectives:** DO1, DO2


### ING-02: Invalid local MQTT ingestion

**Purpose:** Confirm that malformed telemetry received through MQTT does not enter the durable outbox.

**Expected:** the publication is rejected and the ingestion process continues.

**Actual:** Passed.

**Objectives:** DO1


## Outbox and duplicate control

### OUTBOX-01: Valid message persistence

**Purpose:** Confirm that a validated message can be committed to the SQLite WAL outbox.

**Expected:** one `pending` row is created with attempt count zero and the expected telemetry fields.

**Actual:** Passed after the schema was aligned with the repository fields.

**Objectives:** DO2


### OUTBOX-02: Identical retransmission

**Purpose:** Confirm that the same idempotency key and payload hash is treated as an expected retransmission duplicate.

**Expected:** no second outbox row is created and the outcome is `duplicate`.

**Actual:** Passed.

**Evidence:** duplicate-classification repository test and row-count assertion.

**Objectives:** DO4


### OUTBOX-03: Conflicting message content

**Purpose:** Confirm that the same idempotency key with a different payload hash is treated as a data-integrity anomaly.

**Expected:** the original row remains unchanged, no second row is created and the outcome is `conflict`.

**Actual:** Passed.

**Evidence:** conflicting-payload repository test.

**Objectives:** DO4


### DUP-01: Expected retransmission evidence

**Purpose:** Confirm that an expected retransmission is recorded as duplicate-control evidence as well as being rejected from the outbox.

**Expected:** the second copy returns `duplicate`, the outbox remains at one row, one `expected_retransmission` observation is recorded, and the stored and observed payload hashes match.

**Actual:** Passed.

**Evidence:** repository duplicate test and `gateway_duplicate_observations`.

**Objectives:** DO4


### DUP-02: Data-integrity anomaly evidence

**Purpose:** Confirm that conflicting content for an existing idempotency key remains visible without replacing the accepted telemetry.

**Expected:** the outcome is `conflict`, the outbox remains at one row, one `payload_conflict` observation is recorded, the payload hashes differ, and the original payload remains unchanged.

**Actual:** Passed.

**Evidence:** repository conflict test and `gateway_duplicate_observations`.

**Objectives:** DO4


### DUP-03: Collector repeated observation count

**Purpose:** Confirm that repeated observations remain visible at the evaluation collector and can be counted independently from gateway duplicate control.

**Expected:** two observations with the same stable identity and payload hash produce one repeated collector observation.

**Actual:** Passed.

**Evidence:** `test_collector_preserves_repeated_observations`.

**Objectives:** EO2 foundation


### DUP-04: Collector conflicting observation

**Purpose:** Confirm that the collector can identify two observations with the same stable identity but different payload content.

**Expected:** both observations remain stored and the duplicate summary reports one conflicting observation rather than one repeated observation.

**Actual:** Passed.

**Evidence:** collector conflicting-observation test and payload-hash comparison.

**Objectives:** EO2 foundation


## Upstream publication

### UP-01: Successful upstream QoS 1 publication

**Purpose:** Confirm the normal durable state transition when the upstream broker acknowledges a publication.

**Expected:** `pending → in_flight → broker_acknowledged`, attempt count increases and `acknowledged_at` is populated.

**Actual:** Passed.

**Evidence:** `test_successful_publish_becomes_broker_acknowledged`.

**Objectives:** DO2, foundation for EO1


### UP-02: Immediate upstream publication failure

**Purpose:** Confirm that an immediate MQTT publication failure does not become `broker_acknowledged`.

**Expected:** the record moves to `retry_wait` and remains durably available.

**Actual:** Passed.

**Evidence:** `test_publish_error_moves_message_to_retry_wait`.

**Objectives:** DO2, prerequisite for DO3


### UP-03: Upstream acknowledgement timeout

**Purpose:** Confirm that an uncertain QoS 1 publication remains available for later recovery.

**Expected:** the record moves from `in_flight` to `retry_wait` when acknowledgement is not confirmed.

**Actual:** Passed.

**Evidence:** `test_acknowledgement_timeout_moves_message_to_retry_wait`.

**Objectives:** DO2, prerequisite for DO3, foundation for EO2


### UP-04: Empty pending outbox

**Purpose:** Confirm that no publication is attempted when no `pending` record exists.

**Expected:** no state changes and the result is `NO_PENDING`.

**Actual:** Passed.

**Objectives:** DO2


### UP-05: Real upstream Mosquitto publication

**Purpose:** Confirm the publication to a real upstream broker before controlled recovery is added.

**Configuration:** `localhost:1884`, QoS 1, topic `telemetry/sensor-001`, no NetEm impairment.

**Expected:** broker receives the publication, returns `PUBACK`, and the gateway records `broker_acknowledged`.

**Actual:** Passed. The independent subscriber also received the expected publication.

**Conclusion:** Upstream publication works under normal local conditions. This test does not measure resilience under intermittent connectivity.

**Objectives:** DO2, prerequisite for DO3, foundation for EO1


## Evaluation collector


### EVAL-DB-01: Evaluation database initialisation

**Purpose:** Confirm that evaluation evidence is stored separately from gateway operational state.

**Expected:** `evaluation.db` initialises with WAL mode and the collector tables without requiring the gateway outbox database.

**Actual:** Passed.

**Objectives:** foundation for EO1 and EO2


### COL-01: Valid collector observation persistence

**Purpose:** Confirm that a valid upstream observation is stored with run identifier, receipt timestamp, telemetry identity and payload hash.

**Actual:** Passed.

**Evidence:** collector repository tests and `collector_observations` inspection.

**Objectives:** EO1 foundation


### COL-02: Repeated collector observations are preserved

**Purpose:** Confirm that repeated observations of the same telemetry identity remain visible for later duplicate-control measurement.

**Expected:** two arrivals create two collector rows with the same stable identity and payload hash.

**Actual:** Passed.

**Evidence:** `test_collector_preserves_repeated_observations`.

**Objectives:** EO2 foundation


### COL-LIVE-01: Real upstream collector subscription

**Purpose:** Confirm that the evaluation collector can connect to the real upstream broker and subscribe to the telemetry topic.

**Configuration:** broker `localhost:1884`, topic `telemetry/#`, QoS 1, run `baseline-smoke-001`, no NetEm impairment.

**Actual:** Passed. Mosquitto accepted the collector connection and subscription.

**Objectives:** EO1 foundation


## End-to-end evidence

### E2E-01: Single-message publisher-to-collector smoke test

**Purpose:** Confirm the complete path from local publication to independent collector observation.

**Configuration:** message `collector-smoke-001`, local broker `localhost:1883`, upstream broker `localhost:1884`, QoS 1, no NetEm impairment.

**Expected:** the gateway stores the message, publishes it upstream, records broker acknowledgement, and the collector records the same telemetry identity independently.

**Actual:** Passed.

**Observed:** the message moved from `pending` to `broker_acknowledged`, and `evaluation.db` contained the matching collector observation under run `baseline-smoke-001`.

**Conclusion:** Broker acknowledgement and collector observation are independently represented.

**Objectives:** EO1 and EO2 foundation


### E2E-02: Known-set baseline reconciliation

**Purpose:** Confirm that a known set of unique messages can be reconciled across publisher, gateway and collector evidence.

**Configuration:**
- Run: `baseline-050-001`
- Generated messages: 50
- Local broker: `localhost:1883`
- Upstream broker: `localhost:1884`
- MQTT QoS: 1
- No NetEm impairment
- One publisher session
- Source sequences: 1 to 50

**Expected:** all 50 identities appear in publisher and gateway evidence, are acknowledged by the upstream broker and are independently observed by the collector. Payload hashes should match and duplicate observations should not increase delivery completeness above 100%.

**Actual:** Passed.

**Results:**
- Generated unique messages: 50
- Gateway present: 50
- Gateway `broker_acknowledged`: 50
- Collector observations: 50
- Unique expected messages observed: 50
- Missing gateway records: 0
- Missing collector observations: 0
- Duplicate collector observations: 0
- Payload conflicts: 0
- Unexpected collector identities: 0
- Delivery completeness: 100.0%

**Evidence:**
- `evidence/baseline-050-001/publisher_output.csv`
- `evidence/baseline-050-001/reconciliation.csv`
- `evidence/baseline-050-001/summary.json`
- `gateway.db`
- `evaluation.db`
- Mosquitto, gateway and collector logs

**Conclusion:** The baseline measurement path works under normal, unimpaired conditions. The result validates the method used to calculate delivery completeness but does not demonstrate resilience under intermittent connectivity. Formal controlled-recovery and impairment-based evaluation remain outstanding.

**Objectives:** EO1 measurement foundation, EO2 measurement foundation


## Stale `in_flight` recovery

### REC-01: Stale attempt recovery

**Purpose:** Confirm that an old unfinished upstream publication becomes eligible for later recovery.

**Expected:** a stale `in_flight` record moves to `retry_wait`, `attempt_count` remains unchanged and no acknowledgement timestamp is added.

**Actual:** Passed.

**Evidence:** `test_stale_in_flight_message_moves_to_retry_wait`.

**Objectives:** DO3


### REC-02: Recent attempt protection

**Purpose:** Confirm that recovery does not reset an upstream publication attempt that may still be active.

**Expected:** a recent `in_flight` record remains `in_flight` and its attempt count is unchanged.

**Actual:** Passed.

**Evidence:** `test_recent_in_flight_message_is_not_reset`.

**Objectives:** DO3


### REC-03: Other delivery states remain unchanged

**Purpose:** Confirm that stale recovery only affects qualifying `in_flight` records.

**Expected:** records already in `pending`, `retry_wait` or `broker_acknowledged` remain unchanged.

**Actual:** Passed.

**Evidence:** `test_stale_recovery_does_not_change_other_states`.

**Objectives:** DO3


### REC-04: Recovery after database reopening

**Purpose:** Confirm that local persistence allows an interrupted publication attempt to be recovered after the gateway database is closed and reopened.

**Expected:** the durable `in_flight` state survives reopening and, once considered stale, moves to `retry_wait` without increasing `attempt_count`.

**Actual:** Passed.

**Evidence:** `test_stale_in_flight_recovery_survives_database_reopening`.

**Objectives:** DO2, DO3


### REC-05: Manual stale-recovery smoke test

**Purpose:** Confirm the stale recovery path using the real gateway database and upstream publication tool.

**Configuration:**
- Message: `stale-smoke-001`
- Upstream broker: `localhost:1884`
- Stale timeout: configured gateway value
- No NetEm impairment

**Expected:** the stored message moves from `in_flight` to `retry_wait` after restart, without increasing its attempt count or publishing it again.

**Actual:** Passed.

**Observed:**
- `stale-smoke-001` was initially persisted as `pending`.
- The interrupted publication state was simulated as `in_flight` with `attempt_count = 1`.
- After the gateway process was stopped, `publish_pending.py` detected one stale `in_flight` record.
- `stale-smoke-001` moved to `retry_wait`.
- `attempt_count` remained 1.
- `acknowledged_at` remained empty.
- No `in_flight` row remained for the message.
- One `retry_wait` row remained.
- The publisher selected a different `pending` message rather than replaying `stale-smoke-001`.

**Conclusion:** local persistence prevented the interrupted record from being lost. Replay of `retry_wait` records remains separate from this slice.

**Evidence:** gateway runtime log, `publish_pending.py` log and `gateway.db` queries.

**Objectives:** DO2, DO3


## Controlled recovery

### CR-01: Link-stability time

**Purpose:** Confirm that backlog recovery does not begin immediately
after the upstream connection becomes available or after stability has
been lost.

**Configuration:** Use a configurable link-stability interval and a controllable MQTT
client state.

**Expected:** the upstream path must remain connected for the configured
stability period before recovery becomes eligible. The stability
condition is reset after a disconnect or failed publication.

**Actual:** Passed.

**Evidence:** `test_stability_period_is_required_before_recovery`.

**Objectives:** DO3


### CR-02: QoS 1 health publication

**Purpose:** Confirm that a stable connection is checked with a dedicated
QoS 1 health publication before telemetry backlog is released.

**Expected:** an acknowledged health publication allows recovery. A
failed or uncertain health publication prevents the batch from starting.

**Actual:** Passed.

**Evidence:** `test_health_probe_requires_qos1_acknowledgement`.

**Objectives:** DO3


### CR-03: Recovery eligibility and stream ordering

**Purpose:** Confirm that `pending` and `retry_wait` records can be
selected while `in_flight` and `broker_acknowledged` records are
excluded.

**Expected:** source sequence remains ordered within each
`device_id + publisher_session_id` stream.

**Actual:** Passed.

**Evidence:** `test_recovery_selects_pending_and_retry_wait_in_stream_order`

**Objectives:** DO3


### CR-04: Bounded backlog replay

**Purpose:** Confirm that one recovery cycle releases no more than the
configured batch size.

**Expected:** with more eligible records than the batch limit, only one
bounded batch is attempted before the next path check.

**Actual:** Passed.

**Evidence:** `test_recovery_batch_is_bounded`.

**Objectives:** DO3, foundation for EO3


### CR-05: Failure stops the current batch

**Purpose:** Confirm that controlled recovery does not continue releasing
backlog after connectivity becomes uncertain.

**Expected:** an unsuccessful record returns to `retry_wait`, later
records remain unattempted, and the current batch stops.

**Actual:** Passed.

**Evidence:** `test_publication_failure_stops_current_batch`.

**Objectives:** DO2, DO3, foundation for EO2


### CR-06: Recovery resumes after another interruption

**Purpose:** Confirm that a message left in `retry_wait` can be attempted
again after a later stable period.

**Expected:** the later attempt increments `attempt_count` and can reach
`broker_acknowledged` if the upstream broker confirms the publication.

**Actual:** Passed.

**Evidence:** `test_recovery_can_resume_after_failure`.

**Objectives:** DO3, foundation for EO2 and EO3


### CR-07: Limited priority without starvation

**Purpose:** Confirm that priority can influence bounded replay without
breaking source order or indefinitely blocking older backlog.

**Expected:** most selections continue to favour old eligible records,
while limited priority positions can select a higher-priority stream
head.

**Actual:** Passed.

**Evidence:** `test_limited_priority_slot_does_not_break_device_order`.

**Objectives:** DO3


### CR-08: Manual controlled-recovery smoke test

**Purpose:** Confirm controlled backlog replay against a real upstream
Mosquitto broker.

**Configuration:**

- Upstream broker: `localhost:1884`
- Link-stability period: 5 seconds
- Replay batch size: 10
- Health topic: `gateway/health`
- Backlog: 12 telemetry messages
- Two messages initially in `retry_wait`
- Ten messages initially in `pending`
- No NetEm impairment

**Expected:** recovery starts only after the upstream connection has
remained stable and a QoS 1 health publication has been acknowledged.
Eligible telemetry is then released in bounded batches while source
order is preserved.

**Actual:** Passed.

**Observed:**
- Twelve messages were persevered for one device and publisher session.
- Source sequences 1 and 2 were placed in `retry_wait` with
  `attempt_count = 1`; sequences 3 to 12 remained `pending`.
- The upstream connection remained available for approximately 5
  seconds before the first health probe and telemetry recovery.
- Two QoS 1 publications were observed on `gateway/health`.
- The first recovery batch acknowledged ten telemetry messages.
- The second recovery batch acknowledged the remaining two messages.
- Telemetry arrived in source-sequence order from 1 to 12.
- The two `retry_wait` records completed with `attempt_count = 2`.
- The other 10 records completed with `attempt_count = 1`.
- All twelve records finished as `broker_acknowledged`.
- No `pending`, `retry_wait` or `in_flight` record remained for the
  test session.

**Conclusion:** controlled recovery released the durable backlog in
bounded batches after link stability had been established. Durable
retry state, source ordering and broker acknowledgement were preserved.

**Evidence:** Mosquitto broker log, `gateway/health` subscriber,
`telemetry/#` subscriber, controlled-recovery runtime log and
`gateway.db` queries.

**Objectives:** DO3; foundation for EO2 and EO3
