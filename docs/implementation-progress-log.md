# Implementation progress log

## 25/07/2026

Completed:
- Created SQLite database initialisation.
- Enabled WAL mode.
- Added outbox uniqueness constraint.

Problems:
- Duplicate inserts raised an unhandled exception.

Action:
- Add explicit duplicate classification in the repository layer.

TMA03 objectives:
- DO2
- DO4


## 01/08/2026

Branch:
- `feat/baseline-message-contract`

Commit:
- `feat(contract): define telemetry message validation and hashing`

Completed:
- Defined the telemetry message structure using the fields specified in TMA03.
- Implemented the `TelemetryMessage` model.
- Implemented validation for required fields, identifiers, integers, timestamps and payload content.
- Added Coordinated Universal Time normalisation for source timestamps.
- Implemented payload serialisation using canonical JSON.
- Verified and updated SHA-256 payload hashing to support duplicate classification.
- Added tests for valid messages, missing fields, timestamp normalisation and equivalent payload hashing.
- Ran the message-contract test suite successfully after fixed the errors.
- Committed the completed work to the `feat/baseline-message-contract` branch.

Problems:
- Typos error were identified during the completed test run.

Evidence:
- Git branch: `feat/baseline-message-contract`
- Git commit: `feat(contract): define telemetry message validation and hashing`
- Passing automated test output
- `models.py`
- `validation.py`
- `test_validation.py`
- Design decisions D002 and D003

Outcome:
- The telemetry contract is now fixed in code and remains consistent with TMA03.
- Canonical JSON ensures that payloads with the same content but different key ordering produce the same hash.
- The message-contract and validation portion of DO1 is implemented.
- Payload hashing provides part of the implementation required for DO4, although complete duplicate classification still depends on the SQLite repository.

Next step:
- Commit the SQLite WAL database initialisation, outbox repository and persistence tests on `feat/sqlite-outbox`.

TMA03 objectives:
- DO1
- DO4


## 02/08/2026

Branch:
- `feat/sqlite-outbox`

Completed:
- Verified SQLite database initialisation.
- Configured SQLite Write-Ahead Logging mode.
- Enabled foreign-key enforcement for each database connection.
- Added execution of `schema.sql` when the database is initialised.
- Aligned the `outbox_messages` schema with the columns required by the repository.
- Implemented repository-level insertion into the durable outbox.
- Verified that the repository and database schema now operate consistently.
- Ran the repository tests successfully.

Problems identified:
- Mixed tabs and spaces in `database.py` caused indentation and formatting errors.
- The schema path in `test_database.py` did not reliably locate the repository-root `schema.sql` file.
- `open_database()` opened the SQLite database but did not execute `schema.sql`, leaving the required `outbox_messages` table absent.
- The original schema did not contain all columns used by `repository.py`, causing repository insertion failures.

Corrective actions:
- Replaced mixed indentation in `database.py` with consistent four-space indentation.
- Updated the schema path in `test_database.py` to:

  `Path(__file__).resolve().parent.parent / "schema.sql"`

- Added schema execution during database initialisation:

  `connection.executescript(schema_sql)`

- Added the following required columns to `outbox_messages`:

  - `received_at`
  - `topic`
  - `priority`
  - `last_attempt_at`
  - `acknowledged_at`
  - `next_retry_at`

- Retained the existing uniqueness constraints and durable delivery-state checks.

Evidence:
- Passing `test_repository.py` result with exit code 0.
- Updated `database.py`.
- Updated `test_database.py`.
- Updated `schema.sql`.
- Existing design decision D001.
- Git diff for the `feat/sqlite-outbox` branch.

Outcome:
- The database initialiser now creates the required schema.
- The SQLite schema and repository insertion logic are consistent.
- The accepted TMA03 message fields and delivery-state model remain unchanged.
- The corrections restored the implementation to the schema already agreed in D001 rather than introducing a new design.
- Repository-level persistence is now functioning under the current test conditions.

Limitations:
- Passing repository tests confirms local database behaviour but does not yet demonstrate MQTT ingestion, upstream publication or restart recovery.
- DO2 should remain in progress until the full database test suite, including database reopening and persistence checks, has passed.
- End-to-end duplicate control will still require MQTT ingestion and later recovery scenarios.

Next action:
- Run the complete database and repository test set.
- Confirm WAL mode, schema version, persistence after reopening and duplicate/conflict classification.
- Commit the completed SQLite outbox work.
- Create `feat/gateway-ingestion`.
- Connect the local Mosquitto subscription callback to `parse_telemetry_message()` and `store_message()`.

TMA03 objectives:
- DO2
- DO4


## 03/08/2026

Branch:
- `feat/gateway-ingestion`

Started:
- Created the gateway-ingestion implementation slice.
- Defined the settings required for the ingestion slice.

Planned implementation:
- Create the configuration models for the local-first edge gateway.
- Define safe values for the local testing

current status:
- Implemented

TMA03 objectives:


## 04/08/2026

Branch:
- `feat/gateway-ingestion`

Started:
- Defined the slice boundary as local MQTT ingestion through to local
  SQLite persistence.
- Confirmed that upstream publication, retries, link-stability detection,
  controlled recovery and NetEm testing remain outside this slice.

Planned implementation:
- Add local Mosquitto connection configuration.
- Subscribe to the agreed telemetry topic filter at QoS 1.
- Connect the MQTT message callback to `parse_telemetry_message()`.
- Pass validated telemetry to `store_message()`.
- Record inserted, duplicate, conflict, rejected and error outcomes.
- Add focused ingestion tests.
- Complete a real Mosquitto smoke test.

Current status:
- In progress.

TMA03 objectives:
- DO1
- DO2
- DO4


## 07/08/2026

Branch:
- `feat/gateway-ingestion`

Commit:
- `feat(ingestion): persist local MQTT telemetry`

Completed:
- Implemented configuration for the local Mosquitto connection.
- Implemented the local MQTT subscription using the agreed topic filter
  and QoS 1.
- Connected the MQTT callback to `parse_telemetry_message()` and
  `store_message()`.
- Kept validation and SQL logic outside the callback.
- Added structured outcomes for inserted, duplicate, conflict, rejected
  and database-error cases.
- Added ingestion tests.
- Completed a real Mosquitto smoke test.
- Verified that a valid MQTT publication creates one durable `pending`
  outbox row.
- Verified that an identical retransmission does not create another row.
- Verified that malformed JSON does not enter the outbox.

Problems:
- message_id and row_id were defined as required fields in the dataclass. However, process_mqtt_publication does not supply those fields.
- valid_paylod() test failed because returned bytes that were not valid JSON.

Corrective actions:
- Default values (None) were added to message_id and row_id, allowing the dataclass to represent both success and error outcomes consistently.
- valid_payload() returns json.dumps({"temperature_c": 18.5}).encode("utf-8") instead
of b"temperature_c=18.5".

Evidence:
- Passing ingestion tests.
- Passing full test suite.
- Gateway log from the Mosquitto smoke test.
- SQLite query showing the persisted `pending` row.
- Git branch and commit.
- Design decision D005.

Outcome:
- The complete local ingestion path is operational:

  `publisher → local broker → gateway callback → validation → SQLite WAL`

- This demonstrates durable local ingestion but does not yet demonstrate
  upstream publication or controlled recovery.

Limitations:
- Upstream delivery has not yet been implemented.
- Broker acknowledgements have not yet been linked to outbox state.
- NetEm has not yet been applied to the complete MQTT path.

Next action:
- Begin `feat/upstream-publication`.
- Publish eligible `pending` rows to the upstream broker and implement
  the initial acknowledgement-state transition.

TMA03 objectives:
- DO1
- DO2
- DO4


## 08/08/2026

Branch:
- `feat/upstream-publication`

Started:
- Created the upstream-publication implementation slice.
- Defined the settings required for the upstream slice.

Planned implementation:
- Create the configuration models for the local-first edge gateway.
- Define safe values for the local testing

current status:
- Implemented



## 09/08/2026

Branch:
- `feat/upstream-publication`

Implementation slice:
- Upstream MQTT publication

Completed:
- Implemented a separate upstream MQTT client for forwarding telemetry
  already committed to the SQLite WAL outbox.
- Implemented selection of the next eligible `pending` outbox record.
- Kept the baseline publisher deliberately limited to one message per
  publication operation so that uncontrolled backlog replay is not
  introduced before the controlled-recovery slice.
- Implemented the durable transition from `pending` to `in_flight`
  immediately before upstream publication.
- Incremented `attempt_count` and recorded `last_attempt_at` when a
  publication attempt starts.
- Implemented MQTT Quality of Service 1 upstream publication.
- Implemented waiting for the broker acknowledgement before treating a
  publication as successful.
- Implemented the transition from `in_flight` to
  `broker_acknowledged` when the QoS 1 acknowledgement is confirmed.
- Implemented the transition from `in_flight` to `retry_wait` when
  publication cannot be started, fails or the acknowledgement is not
  confirmed within the configured timeout.
- Added a `NO_PENDING` outcome so that an empty outbox is handled without
  an error or unnecessary MQTT publication.
- Added structured publication results containing the outbox row,
  message identifier, MQTT message identifier and publication outcome.
- Added automated tests covering successful acknowledgement, immediate
  MQTT publication failure, acknowledgement timeout and an empty outbox.
- Completed a real upstream Mosquitto smoke test and confirmed successful
  QoS 1 publication, broker acknowledgement, subscriber receipt and
  durable SQLite state transition.

Problems identified:
- The first complete upstream test run produced four failures in
  `tests/test_upstream.py`.
- All four failures initially originated from the same SQL statement in
  `get_next_pending_message()` rather than from separate upstream
  publication problems.
- The `SELECT` statement contained a trailing comma after
  `attempt_count`, causing SQLite to raise:

  `sqlite3.OperationalError: near "FROM": syntax error`

- Because the query failed before returning an outbox row, none of the
  four upstream tests reached the MQTT publication logic during that
  run.
- After correcting the SQL syntax, the tests progressed into the
  repository state-transition logic.
- Three tests then failed because `mark_in_flight()` assigned the current
  timestamp to a variable named `row` but attempted to use an undefined
  variable named `now`.
- The empty-outbox test failed because `get_next_pending_message()` did
  not handle `fetchone()` returning `None`.
- During the real smoke-test preparation, the standalone
  `tools/publish_pending.py` script initially failed to locate the
  `edge_gateway` package because of the project's Python import path.
- A later configuration error was also identified because
  `broker_port` was represented as a string rather than an integer,
  causing configuration validation to raise a `TypeError`.

Corrective actions:
- Removed the trailing comma after `attempt_count` in
  `get_next_pending_message()`.
- Changed the SQL delivery-state comparison to use the string literal
  `'pending'`.
- Added an explicit `if row is None: return None` guard to
  `get_next_pending_message()`.
- Retained deterministic pending-message selection using
  `source_timestamp ASC, id ASC`.
- Changed `row = utc_now()` to `now = utc_now()` in
  `mark_in_flight()`.
- Reviewed the remaining state-transition functions for consistent
  timestamp handling.
- Corrected the standalone execution environment so that
  `publish_pending.py` could import the project modules.
- Corrected `broker_port` so that it is stored as an integer rather than
  a string.
- Re-ran the affected tests after each correction before proceeding to
  the real broker smoke test.

Initial test evidence:
- The full test suite initially collected 15 tests.
- 11 existing database, ingestion, repository and validation tests
  passed.
- Four new upstream-publication tests initially failed because of the
  shared SQL syntax error.
- The existing implementation therefore remained stable while defects in
  the new upstream-publication slice were isolated and corrected.

Initially failing tests:

- `test_successful_publish_becomes_broker_acknowledged`
- `test_publish_error_moves_message_to_retry_wait`
- `test_acknowledgement_timeout_moves_message_to_retry_wait`
- `test_no_pending_message_returns_without_publishing`

Final verification:
- Re-ran the upstream automated tests after correcting the repository
  implementation.
- The focused upstream-publication tests passed.
- Completed a real Mosquitto smoke test using an upstream broker on port
  1884.
- The `edge-gateway-upstream` client connected successfully and published
  `msg-smoke-002` to `telemetry/sensor-001` using MQTT QoS 1.
- The Mosquitto broker log confirmed receipt of the QoS 1 `PUBLISH` and
  transmission of the corresponding `PUBACK`.
- An independent `mosquitto_sub` client subscribed to `telemetry/#`
  received the expected payload:

  `{"temperature_c":18.5}`

- The gateway reported:

  `outcome=broker_acknowledged row_id=2 message_id=msg-smoke-002 mid=1`

- SQLite inspection confirmed that the message remained durably recorded
  with:

  - `delivery_state = broker_acknowledged`
  - `attempt_count = 1`
  - populated `last_attempt_at`
  - populated `acknowledged_at`

Smoke-test evidence:

- Upstream broker: `localhost:1884`
- Gateway MQTT client: `edge-gateway-upstream`
- Topic: `telemetry/sensor-001`
- QoS: 1
- Message: `msg-smoke-002`
- MQTT message identifier: 1
- Subscriber receipt: confirmed
- Broker `PUBACK`: confirmed
- Durable SQLite acknowledgement state: confirmed

Evidence:
- `src/upstream.py`
- Updated `src/repository.py`
- Upstream configuration in `src/config.py`
- `tools/publish_pending.py`
- `tests/test_upstream.py`
- Initial pytest output showing 11 passed and 4 failed.
- Subsequent passing focused upstream tests.
- Mosquitto broker log.
- Independent subscriber output.
- Gateway publication log.
- SQLite state inspection.
- Corrected `get_next_pending_message()` query.
- Design decision D006.

Outcome:
- The implementation now connects durable local persistence to the
  upstream MQTT publication path.
- A selected message is placed in `in_flight` before publication so that
  the database records that a transmission attempt has begun.
- Confirmed QoS 1 acknowledgement changes the durable state to
  `broker_acknowledged`.
- Failed or uncertain publication changes the durable state to
  `retry_wait`.
- The implementation preserves the acknowledgement uncertainty described
  in TMA03 rather than assuming that an attempted publication was
  delivered successfully.
- The real smoke test demonstrated successful broker acknowledgement and
  independent subscriber receipt under normal local network conditions.
- Broker acknowledgement remains distinct from formal end-to-end
  collector evidence.

Limitations:
- `broker_acknowledged` proves interaction with the upstream broker only.
  It does not yet prove that the evaluation collector received the
  telemetry.
- `retry_wait` records are not yet automatically rescheduled.
- Stale `in_flight` recovery is not implemented in this slice.
- Link-stability detection is not implemented.
- Bounded backlog replay is not implemented.
- Priority-aware recovery scheduling is not implemented.
- NetEm impairment has not yet been applied to this complete publication
  path.

Relationship to TMA03:
- Implements the durable transitions defined in the TMA03
  outbox state model:
  `pending → in_flight → broker_acknowledged`
- Implements failure handling:
  `in_flight → retry_wait`
- Establishes the acknowledgement-handling foundation required before
  stale `in_flight` recovery and controlled recovery are implemented.
- Does not claim that controlled recovery, DO3, has been completed.

Next action should be:
- run the complete automated test suite once more before closing the
  branch, if this has not already been done after the final corrections.
- Keep the broker, publisher, subscriber and SQLite smoke-test
  outputs as implementation evidence.
- Commit the verified `feat/upstream-publication` slice.
- Merge the completed slice into the project baseline and confirm that
  the complete test suite remains green.
- Start `feat/evaluation-collector`.
- Use the publisher and collector evidence later to calculate delivery
  completeness under EO1.

  TMA03 objectives:

- DO2: extends durable local persistence into durable upstream
  delivery-state tracking.
- DO3: provides a prerequisite for controlled recovery; link-stability
  detection and bounded replay remain outstanding.
- EO1: establishes the upstream publication path required for later
  collector-based delivery-completeness measurement.
- EO2: establishes acknowledgement and retransmission behaviour required
  for later duplicate-control evaluation.


  ## 09/08/2026

  Branch:

  - `feat/evaluation-collector`

  Implementation slice:

  - Evaluation collector

  Completed:

  - Added a MQTT evaluation collector for observing
    publications sent through the upstream broker.
  - Configured the collector to subscribe to `telemetry/#` using MQTT
    QoS 1.
  - Added a separate `evaluation.db` database for experimental evidence
    while keeping `gateway.db` exclusively for gateway operational state.
  - Added `evaluation_schema.sql` for collector observations and rejected
    messages.
  - Reused the existing database and repository modules rather than
    introducing separate evaluation modules.
  - Added run identifiers so that collector observations can be linked
    with individual experimental runs.
  - Recorded collector timestamps, MQTT topic and QoS metadata,
    stable message identity, source sequence, source timestamp, priority,
    payload and payload hash.
  - Preserved raw MQTT message content for later diagnostic and evaluation
    evidence.
  - Deliberately kept repeated collector observations rather than
    deleting the duplicates, allowing all deliveries to
    remain visible for later EO2 evaluation.
  - Added automated repository testing confirming that repeated
    observations with the same message identity are stored as separate
    collector records.
  - Ran the complete automated test suite successfully.
  - Started a real evaluation collector using run identifier
    `baseline-smoke-001`.
  - Verified successful connection and subscription to the upstream
    Mosquitto broker on `localhost:1884`.

  Problems identified:

  - The first collector repository test failed because the test referenced
    a helper function that had not been defined in
    `tests/test_repository.py`.
  - After correcting the test, the collector repository test
    progressed into persistence logic and exposed an incorrect `payload_hash`
    attribute assigned to `TelemetryMessage` where the correct name is `payload`.
  - `payload_hash` is derivative evidence rather than part of the incoming
    telemetry payload.
  - The collector test also required a clear distinction between the parsed
    telemetry structure and the raw MQTT bytes retained as evaluation
    evidence.
  - During the initial real smoke test, the collector subscribed
    successfully and the local gateway stored `collector-smoke-001`, but
    the message remained in `pending` state because upstream
    publication had not yet been invoked. Hence, `evaluation.db` correctly
    does not collect observation at that point.

  Corrective actions:

  - Added a valid telemetry test helper for repository tests.
  - Changed collector persistence to calculate the payload hash using the
    existing payload-hash function.
  - Kept `payload_hash` outside `TelemetryMessage`, preserving the agreed
    telemetry contract.
  - Ensured that raw collector evidence is represented as MQTT-style UTF-8
    bytes rather than as a dictionary.
  - Verified that two observations of the same stable message identity
    produce two rows in `collector_observations`.
  - Began consolidating repeated test builders such as `valid_message`,
    `valid_payload` and `valid_message_bytes` into a shared
    `tests/helpers.py` module.
  - Kept separate SQLite databases files while sharing the existing database
    and repository modules to avoid unnecessary code.

  Automated verification:

  - All automated tests passed after the collector repository corrections.
  - The upstream identity-preservation test remains passing.
  - Repeated collector observations are retained rather than silently
    deduplicated.
  - Existing database, ingestion, validation, repository and upstream
    publication behaviour remains green.

  Initial real smoke-test evidence:

  - Upstream Mosquitto broker started successfully on `localhost:1884`.
  - Evaluation collector client:
    `edge-gateway-evaluation-collector`
  - Evaluation run:
    `baseline-smoke-001`
  - Subscription:
    `telemetry/#`
  - QoS:
    1
  - Collector subscription was accepted by the upstream broker.
  - Local gateway received:
    `collector-smoke-001`
  - Gateway persisted the message with:
    `delivery_state = pending`
  - No collector observation was present before upstream publication,
    which is the expected result while the message remains local.


  End-to-end verification:

  - Passed.
  - `collector-smoke-001` was accepted by the local gateway and committed to the SQLite WAL outbox with initial state `pending`.
  - The baseline upstream publisher selected the pending record and forwarded the complete telemetry envelope to the upstream Mosquitto broker using MQTT QoS 1.
  - The upstream broker confirmed receipt of the publication and returned `PUBACK` to the `edge-gateway-upstream` client.
  - The gateway changed the durable outbox state from `pending` through  `in_flight` to `broker_acknowledged`.
  - SQLite confirmed:
    - `delivery_state = broker_acknowledged`
    - `attempt_count = 1`
    - populated `acknowledged_at`
  - The upstream broker forwarded the same publication to the independent `edge-gateway-evaluation-collector` client.
  - The broker subsequently received `PUBACK` from the evaluation collector.
  - The evaluation collector persisted an independent observation under run identifier `baseline-smoke-001`.
  - `evaluation.db` retained:
    - `message_id = collector-smoke-001`
    - `device_id = sensor-001`
    - `publisher_session_id = session-collector-001`
    - `source_sequence = 1`
    - collector receipt timestamp
    - canonical payload hash
  - The matching collector payload hash was: `41bffd2bb7d92e8839969485a2cff7d87b1297fd660e5fb28e6a8c82a9f1db3e`
  - This demonstrates the complete path from local telemetry publication to independent downstream receipt evidence.

  Evidence:

  - Local gateway database row:
    `3|collector-smoke-001|pending` before upstream publication.
  - Upstream publication result:
    `outcome=broker_acknowledged row_id=3 message_id=collector-smoke-001 mid=1`
  - Final gateway database state:
    `3|collector-smoke-001|broker_acknowledged|1|...`
  - Evaluation run:
    `baseline-smoke-001`
  - Evaluation collector:
    `edge-gateway-evaluation-collector`
  - Upstream broker:
    `localhost:1884`
  - Topic:
    `telemetry/sensor-001`
  - MQTT QoS:
    1
  - Broker acknowledgement to gateway:
    confirmed.
  - Broker forwarding to collector:
    confirmed.
  - Collector acknowledgement to broker:
    confirmed.
  - Independent collector database observation:
    confirmed.

  Outcome:

  - The publisher-to-collector measurement path is operational.
  - Broker acknowledgement and collector observation are now separate pieces of evidence.
  - Telemetry identity is preserved across the gateway, upstream publication and evaluation collector.
  - The collector can now provide independent evidence needed for later delivery-completeness and duplicate-control evaluation.

  Limitations:

  - Delivery completeness has not yet been calculated.
  - The current live smoke test does not yet demonstrate the complete
    publisher-to-collector path.
  - Duplicate observations are preserved but formal duplicate
    classification and EO2 measurement remain outstanding.
  - Stale `in_flight` recovery remains outstanding.
  - Link-stability detection and bounded backlog replay remain outstanding.
  - NetEm impairment has not yet been applied to the complete MQTT
    publisher-to-collector path.

  Relationship to TMA03:

  - Implements the independent evaluation collector required to distinguish
    broker acknowledgement from downstream receipt evidence.
  - Supports the publisher-to-collector evidence path planned in TMA03.
  - Provides the measurement foundation for EO1 and EO2.
  - Does not yet constitute formal evaluation evidence under degraded
    network conditions.

  Next action:

  - Keep the gateway, broker and evaluation-database outputs as implementation evidence.
  - Commit and merge `feat/evaluation-collector`.
  - Begin the next recovery-focused slice.
  - Implement the mechanisms required to recover uncertain or interrupted
    upstream publication before introducing bounded controlled replay.

  TMA03 objectives:

  - EO1: implementation foundation and independent receipt evidence.
  - EO2: implementation foundation through preservation of repeated
    observations.
  - Supports later DO3 recovery evaluation.
