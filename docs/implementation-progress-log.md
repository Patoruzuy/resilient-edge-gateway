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
- Implemented SHA-256 payload hashing to support duplicate classification.
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
- Implemented SQLite database initialisation.
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
