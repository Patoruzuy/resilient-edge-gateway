# Objective Traceability Matrix

Created: 20/07/2026
Last updated: 09/08/2026

This matrix links the development and evaluation objectives defined in
TMA03 to their implementation, planned evidence and current status.

| Objective | Implementation | Planned evidence | Current status |
|---|---|---|---|
| DO1 | Telemetry message contract, validation, timestamp normalisation, canonical payload handling and local MQTT ingestion | Passing validation and ingestion tests, malformed-message rejection and local Mosquitto testing | Implemented |
| DO2 | SQLite WAL outbox, durability boundary, persistent delivery state and baseline upstream state transitions | Schema and WAL verification, persistence tests, database reopening tests, upstream transition tests and real QoS 1 Mosquitto smoke test | Implemented |
| DO3 | Link-stability detection and bounded backlog replay | Recovery logs, scheduler tests and outage/reconnection integration tests | Not started |
| DO4 | Composite idempotency key, SQLite uniqueness constraints and canonical payload-hash comparison | Duplicate retransmission tests, conflicting-payload tests and classification evidence | Implemented |

| EO1 | Upstream evaluation collector with specific observation evidence | Passing publisher-to-collector smoke test; later publisher-manifest reconciliation and delivery-completeness calculation | In progress |
| EO2 | Duplicate observations across gateway and collector evidence | Duplicate counts, retransmission scenarios and duplicate-control results | In progress |
| EO3 | Recovery timing and backlog-state timestamps | Backlog drain-time results under defined outage and recovery scenarios | Not started |
| EO4 | SQLite database and transaction measurements | Database-size records, transaction counts and storage-growth measurements | Not started |
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

The implementation validates required fields, normalises timestamps to
UTC and uses canonical JSON representation for deterministic payload
handling.

The local MQTT ingestion path also connects the Mosquitto subscription
callback to telemetry validation and durable SQLite persistence.

DO1 is currently classified as **Implemented** because the message
contract, validation pipeline and local ingestion behaviour are present
and have been tested.

### DO2

The gateway uses an SQLite Write-Ahead Logging (WAL) outbox as the
durability boundary for accepted telemetry.

The durable state model currently supports:

`pending → in_flight → broker_acknowledged`

and:

`in_flight → retry_wait`

A real Mosquitto smoke test has also demonstrated successful QoS 1
publication to the upstream broker and durable recording of the broker
acknowledgement.

DO2 is therefore classified as **Implemented**. Formal storage-behaviour
measurement remains part of EO4 rather than DO2 implementation.

### DO3

Upstream publication provides the transport and durable state
transitions required by controlled recovery, but controlled recovery
itself has not yet been implemented.

Outstanding DO3 work includes:

- link-stability detection;
- health publications;
- retry eligibility;
- bounded backlog replay;
- replay interruption handling;
- ordering and limited priority behaviour.

DO3 therefore remains **Not started**.

### DO4

The idempotency key is:

`device_id + publisher_session_id + source_sequence`

SQLite uniqueness constraints prevent a second durable row from being
created for the same identity. Canonical payload hashing enables the
gateway to distinguish between an expected retransmission and conflicting
content.

DO4 is classified as **Implemented** once the duplicate and conflicting
payload tests are confirmed as passing.

--------------------------------------------------------------------------------

### EO1

An independent evaluation collector has now been implemented with a
separate SQLite evidence database and evaluation run identifiers.

Automated tests confirm that valid collector observations can be kept
with stable message identity, receipt timestamps and payload hashes. A
real collector has also connected successfully to the upstream Mosquitto
broker.

EO1 still **In progress** because delivery completeness has not yet been
calculated against a publisher manifest. The current end-to-end smoke test
must also complete the upstream publication step before the matching collector observation can be confirmed.

### EO2

Gateway-level duplicate classification is already implemented under DO4.

The evaluation collector now deliberately preserves repeated
observations of the same stable message identity. Automated testing
confirms that repeated arrivals produce separate evidence rows rather
than being silently deduplicated.

EO2 stays **In progress** because the recovery scenarios have not yet
been used to quantify expected retransmissions, conflicting content and
collector-observed duplicates.

### EO5

Exploratory NetEm work has confirmed that delay and packet loss can be
introduced.

Formal impairment-based evaluation has not yet begun because the
publisher-to-collector measurement path and controlled recovery
implementation remain outstanding.

EO5 therefore remains **Exploratory only**.
