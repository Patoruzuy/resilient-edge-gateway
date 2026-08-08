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
To be completed.

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
To be completed.

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
To be completed.

TMA03 objectives:
- DO2
