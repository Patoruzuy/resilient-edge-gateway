# Objective Traceability Matrix

Created: 20/07/2026
Last updated: 01/08/2026

This matrix links the development and evaluation objectives defined in
TMA03 to their implementation, planned evidence and current status.

| Objective | Implementation | Planned evidence | Current status |
|---|---|---|---|
| DO1 | Telemetry message contract, validation, timestamp normalisation and canonical payload handling | Validation unit tests, malformed-message tests and rejection logs | Implemented |
| DO2 | SQLite WAL outbox and durable message-state storage before upstream publication | Schema inspection, WAL verification, persistence tests and restart tests | Implemented |
| DO3 | Link-stability detection and bounded backlog replay | Recovery logs, scheduler tests and outage/reconnection integration tests | Not started |
| DO4 | Composite idempotency key, SQLite uniqueness constraints and payload-hash comparison | Duplicate retransmission tests, conflicting-payload tests and classification evidence | Implemented |

| EO1 | Publisher manifest and evaluation collector manifest | Delivery-completeness calculation after controlled recovery | Not started |
| EO2 | Duplicate observations across gateway and collector evidence | Duplicate counts, retransmission scenarios and duplicate-control results | Not started |
| EO3 | Recovery timing and backlog-state timestamps | Backlog drain-time results under defined outage scenarios | Not started |
| EO4 | SQLite database and transaction measurements | Database-size records, transaction counts and persistence-overhead results | Not started |
| EO5 | Linux traffic control and NetEm scenario configuration | Recorded impairment commands, parameter sets and repeated trials | Exploratory only |

## Status definitions

- **Not started:** No implementation or experimental work has begun.
- **In progress:** Design or implementation exists, but the required tests and evidence are not complete.
- **Exploratory only:** Preliminary work has validated the method or tooling, but formal evaluation has not begun.
- **Implemented:** The feature is present and its focused tests pass.
- **Evaluated:** Formal experimental evidence has been collected and analysed.
- **Complete:** The objective has been implemented, evaluated where applicable, documented and supported by final evidence.

## Current implementation notes

### DO1

The telemetry message contract has been defined using:

- `message_id`
- `device_id`
- `publisher_session_id`
- `source_sequence`
- `source_timestamp`
- `priority`
- `payload`

Canonical JSON and SHA-256 hashing have also been selected. DO1 remains
in progress until the validation tests pass and malformed MQTT input is
shown to be rejected correctly.

### DO2

The SQLite WAL schema, schema version and outbox state model have been
defined. Database initialisation and WAL configuration have begun. DO2
remains in progress until persistence, database reopening and restart
behaviour are confirmed by automated tests.

### DO4

The idempotency key is formed from:

`device_id + publisher_session_id + source_sequence`

SQLite uniqueness constraints and payload hashes support classification
of expected retransmissions and conflicting content. DO4 remains in
progress until duplicate and conflict tests pass without creating
additional outbox rows.

### EO5

Exploratory NetEm work has confirmed that delay and packet loss can be
introduced. Formal evaluation has not yet begun because the complete
publisher-to-collector path and controlled recovery implementation are
still outstanding.
