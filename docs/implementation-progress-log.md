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
