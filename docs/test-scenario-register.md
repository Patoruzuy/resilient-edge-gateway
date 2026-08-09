# Test scenario register

## DB-01: Database initialisation

Purpose:
Verify that a new gateway database is created using the agreed schema.

Configuration:
- Fresh SQLite database path
- Repository-root `schema.sql`
- No MQTT broker required
- No NetEm impairment

Expected:
- `schema.sql` is executed
- `outbox_messages` is created
- SQLite WAL mode is active
- Schema version is 1

Actual:
Passed after correcting database initialisation and schema path handling.

Problems found:
- The schema script was not originally executed.
- The test used an unreliable schema path.
- Indentation errors were present in `database.py`.

Evidence:
- Passing database test output
- Updated `database.py`
- Updated `test_database.py`
- Git commit on `feat/sqlite-outbox`

TMA03 objectives:
- DO2

## VAL-01: Valid telemetry message

Purpose:
Verify that a valid telemetry payload is accepted and converted into the
agreed `TelemetryMessage` representation.

Expected:
- Required fields are accepted.
- Source timestamp is normalised to UTC.
- Canonical payload representation can be generated.

Actual:
Passed.

TMA03 objectives:
- DO1

## VAL-02: Malformed telemetry rejection

Purpose:
Verify that malformed JSON or a message missing a required field is
rejected before durable persistence.

Expected:
- Validation fails with an appropriate reason code.
- No outbox row is created.

Actual:
Passed.

TMA03 objectives:
- DO1

## ING-01: Valid local MQTT ingestion

Purpose:
Verify that a valid publication received from the local MQTT ingestion
path is validated and committed to the SQLite WAL outbox.

Expected:
- Publication is accepted.
- One `pending` row is created.
- MQTT topic is recorded.
- Gateway process continues normally.

Actual:
Passed.

TMA03 objectives:
- DO1
- DO2

## ING-02: Invalid local MQTT ingestion

Purpose:
Verify that malformed telemetry received through the MQTT ingestion path
does not enter the durable outbox.

Expected:
- Publication is classified as rejected.
- No outbox row is created.
- The MQTT ingestion process remains operational.

Actual:
Passed.

TMA03 objectives:
- DO1

## OUTBOX-01: Valid message persistence

Purpose:
Verify that a validated telemetry message can be committed to the
SQLite WAL outbox.

Configuration:
- No MQTT broker required
- Valid `TelemetryMessage`
- One repository insertion
- No NetEm impairment

Expected:
- One `pending` outbox row
- Attempt count set to zero
- Message fields stored correctly
- No duplicate or conflict outcome

Actual:
Passed after aligning `schema.sql` with the repository insert fields.

Problems found:
- The original schema omitted columns required by `repository.py`.

Evidence:
- Passing `test_repository.py`
- SQLite schema
- Repository test output
- Git commit on `feat/sqlite-outbox`

TMA03 objectives:
- DO2


## OUTBOX-02: Identical retransmission

Purpose:
Verify that an identical idempotency key and payload hash is classified
as an expected duplicate.

Expected:
- Original row remains unchanged
- No second outbox row is created
- Outcome is `duplicate`

Actual:
Passed

Observed:
- The second message with the same idempotency key and payload hash was
  classified as `duplicate`.
- No additional outbox row was created.
- The original durable record remained unchanged.

Evidence:
- Passing duplicate-classification repository test.
- SQLite row-count assertion.
- `repository.py`.

TMA03 objectives:
- DO4


## OUTBOX-03: Conflicting message content

Purpose:
Verify that the same idempotency key with a different payload hash is
classified as a data-integrity anomaly.

Expected:
- Original row remains unchanged
- No second outbox row is created
- Outcome is `conflict`

Actual:
Passed.

Observed:
- The same idempotency key with a different payload hash was classified
  as `conflict`.
- No additional outbox row was created.
- The original message remained unchanged.

Evidence:
- Passing conflicting-payload repository test.
- SQLite row-count assertion.
- `repository.py`.

TMA03 objectives:
- DO4


## DB-02: Persistence after reopening

Purpose:
Verify that a committed outbox row remains available after the database
connection is closed and reopened.

Expected:
- The row remains present
- Its state remains `pending`
- Its message identity and payload remain unchanged

Actual:
Passed.

Observed:
- The database connection was closed and reopened.
- The committed message remained present.
- Its `pending` state, identity and stored payload were preserved.

Evidence:
- Passing database-reopening persistence test.
- SQLite inspection after reopening.

TMA03 objectives:
- DO2


## UP-01: Successful upstream QoS 1 publication

Purpose:
Verify that a durable pending message is published to the upstream MQTT
client and becomes `broker_acknowledged` when the QoS 1 acknowledgement
is confirmed.

Configuration:
- One valid `pending` SQLite outbox record
- MQTT QoS 1
- Fake MQTT client returning successful publication
- MQTT message identifier: 27
- No NetEm impairment

Expected:
- The selected row changes from `pending` to `in_flight`.
- `attempt_count` increases by one.
- The stored topic and payload are passed to the MQTT client.
- QoS is 1.
- Retain is disabled.
- A successful acknowledgement changes the row to
  `broker_acknowledged`.
- `acknowledged_at` is populated.

Initial actual result:
- Failed before MQTT publication logic was reached.
- `get_next_pending_message()` raised
  `sqlite3.OperationalError: near "FROM": syntax error`.
- Cause: trailing comma after `attempt_count` in the SELECT statement.

Corrective action:
- Removed the trailing comma from the query.
- Corrected the SQL string literal for the pending state.

Final actual result:
- Passed after correcting the repository implementation.
- The message changed from `pending` to `in_flight` before publication.
- `attempt_count` increased to 1.
- The fake MQTT client received the expected topic and payload at QoS 1.
- Successful acknowledgement changed the durable state to
  `broker_acknowledged`.
- `acknowledged_at` was populated.

Evidence:
- `tests/test_upstream.py::test_successful_publish_becomes_broker_acknowledged`
- Initial pytest output
- Corrected `repository.py`

TMA03 objectives:
- DO2
- Supports later DO3 and EO1


## UP-02: Immediate upstream publication failure

Purpose:
Verify that an upstream publication that cannot be successfully queued
does not become `broker_acknowledged`.

Configuration:
- One valid `pending` SQLite outbox record
- MQTT QoS 1
- Fake MQTT client returning `MQTT_ERR_NO_CONN`
- No NetEm impairment

Expected:
- The row first changes to `in_flight`.
- `attempt_count` increases.
- The failed publication changes the row to `retry_wait`.
- No broker acknowledgement timestamp is recorded.

Initial actual result:
- Failed before MQTT publication logic was reached because of the shared
  SQL syntax error in `get_next_pending_message()`.

Corrective action:
- Corrected the SELECT statement.

Final actual result:
- Passed after correcting the repository implementation.
- The message changed to `in_flight` before the publication attempt.
- The simulated MQTT publication failure resulted in the durable state
  changing to `retry_wait`.
- The message was not incorrectly marked as `broker_acknowledged`.

Evidence:
- `tests/test_upstream.py::test_publish_error_moves_message_to_retry_wait`
- Initial pytest output
- Corrected `repository.py`

TMA03 objectives:
- DO2
- Prerequisite for DO3


## UP-03: Upstream acknowledgement timeout

Purpose:
Verify that an uncertain QoS 1 publication is retained for later recovery
rather than being incorrectly marked as successfully acknowledged.

Configuration:
- One valid `pending` SQLite outbox record
- MQTT QoS 1
- Publication accepted by the fake client
- Broker acknowledgement not confirmed before timeout
- No NetEm impairment

Expected:
- The row changes to `in_flight` when the attempt begins.
- `attempt_count` increases.
- Failure to confirm the acknowledgement changes the row to `retry_wait`.
- The message remains durably available for a later recovery attempt.

Initial actual result:
- Failed before acknowledgement handling was reached because of the
  shared SQL syntax error in `get_next_pending_message()`.

Corrective action:
- Corrected the SELECT statement.

Final actual result:
- Passed after correcting the repository implementation.
- Failure to confirm the QoS 1 acknowledgement resulted in the message
  changing from `in_flight` to `retry_wait`.
- The message remained durably available for later recovery rather than
  being incorrectly recorded as successfully acknowledged.

Evidence:
- `tests/test_upstream.py::test_acknowledgement_timeout_moves_message_to_retry_wait`
- Initial pytest output
- Corrected `repository.py`

TMA03 objectives:
- DO2
- Prerequisite for DO3
- Foundation for EO2 acknowledgement-uncertainty evaluation


## UP-04: Empty pending outbox

Purpose:
Verify that the baseline upstream worker handles an empty pending queue
without attempting an MQTT publication.

Configuration:
- SQLite database containing no `pending` outbox records
- Fake MQTT client
- No NetEm impairment

Expected:
- No MQTT publication is attempted.
- No database row is modified.
- The result is `NO_PENDING`.
- The operation exits normally.

Initial actual result:
- Failed during pending-record selection because of the shared SQL syntax
  error in `get_next_pending_message()`.

Corrective action:
- Corrected the SELECT statement.

Final actual result:
- Passed after adding explicit handling for `fetchone()` returning
  `None`.
- No MQTT publication was attempted.
- No outbox state was modified.
- The operation returned `NO_PENDING` normally.

Evidence:
- `tests/test_upstream.py::test_no_pending_message_returns_without_publishing`
- Initial pytest output
- Corrected `repository.py`

TMA03 objectives:
- Supporting implementation for DO2

## UP-05: Real upstream Mosquitto publication

Purpose:
Verify the baseline upstream publication path using a real MQTT broker
and an independent subscriber.

Configuration:
- Upstream Mosquitto broker: `localhost:1884`
- Gateway client: `edge-gateway-upstream`
- Subscriber topic filter: `telemetry/#`
- MQTT QoS: 1
- Source topic: `telemetry/sensor-001`
- Message identifier: `msg-smoke-002`
- Payload: `{"temperature_c":18.5}`
- No NetEm impairment

Expected:
- Gateway connects to the upstream broker.
- Pending telemetry is published using QoS 1.
- Broker returns PUBACK.
- Independent subscriber receives the expected topic and payload.
- SQLite state changes to `broker_acknowledged`.
- `attempt_count` becomes 1.
- `last_attempt_at` and `acknowledged_at` are populated.

Actual:
Passed.

Observed:
- Mosquitto accepted the `edge-gateway-upstream` connection.
- Broker received a QoS 1 PUBLISH for `telemetry/sensor-001`.
- Broker sent PUBACK for MQTT message identifier 1.
- Independent subscriber received:

  `telemetry/sensor-001 {"temperature_c":18.5}`

- Gateway reported:

  `outcome=broker_acknowledged row_id=2 message_id=msg-smoke-002 mid=1`

- SQLite contained:

  `2|msg-smoke-002|broker_acknowledged|1|...|...`

Conclusion:
- The baseline upstream publication path operates correctly under normal
  local network conditions.
- The result demonstrates broker acknowledgement and subscriber receipt
  for this smoke test.
- It does not yet constitute formal collector-based delivery-completeness
  evidence.

TMA03 objectives:
- DO2
- Supports DO3
- Foundation for EO1
