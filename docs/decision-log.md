# Design Decision Log

## D001: Initial SQLite WAL outbox schema

Date: 25/07/2026
Status: Accepted

### TMA03 position

The gateway stores accepted telemetry and its durable delivery state
before upstream publication. The message model includes a message
identifier, device identifier, publisher session identifier, source
sequence number, source timestamp, priority, payload and payload hash.

TMA03 also defines four durable delivery states: pending, in_flight,
retry_wait and broker_acknowledged.

### Decision

Use a single `outbox_messages` table containing the four delivery states
defined in TMA03.

The idempotency key is formed from:

`device_id + publisher_session_id + source_sequence`

The table also records publication attempts, retry eligibility,
acknowledgement time and local processing timestamps.

### Reason

A single outbox table provides a clear source of durable delivery state.
The additional timing and attempt fields support restart recovery,
acknowledgement handling, backlog drain time measurement and
implementation evidence.

### Relationship to TMA03

This decision is consistent with the design described in TMA03. The
additional timing and retry columns provide implementation detail for
the recovery and evaluation behaviour already proposed.

### Final-report action

Describe the implemented schema and explain how the timing, retry and
acknowledgement fields support controlled recovery and evaluation.


## D002: Telemetry message contract

Date: 26/07/2026
Status: Accepted

### TMA03 position

TMA03 proposes a telemetry message containing a message identifier,
device identifier, publisher session identifier, source sequence number,
source timestamp, priority and payload.

### Decision

The implementation uses the following message fields:

- `message_id`
- `device_id`
- `publisher_session_id`
- `source_sequence`
- `source_timestamp`
- `priority`
- `payload`

The MQTT topic is supplied separately through the MQTT message envelope
and is stored alongside the validated telemetry message.

### Reason

Keeping the topic separate reflects MQTT operation because the topic is
provided by the broker callback rather than being part of the JSON
payload. The remaining fields form the telemetry message contract used
for validation, persistence and duplicate control.

### Relationship to TMA03

This decision is consistent with the telemetry message structure
described in TMA03. Treating the topic as part of the MQTT envelope is an
implementation detail and does not change the proposed message contract.

### Final-report action

Present the final telemetry message structure and explain that the MQTT
topic is received separately by the gateway subscription callback.


## D003: Canonical payload hashing

Date: 29/07/2026
Status: Accepted

### TMA03 position

TMA03 proposes using a payload hash with the idempotency key to
distinguish an expected retransmission from a data-integrity anomaly.

### Decision

Payloads are serialised as UTF-8 JSON using sorted keys, compact
separators and no non-standard numeric values. A SHA-256 hash is then
calculated from the resulting canonical JSON representation.

### Reason

Equivalent JSON objects may use different key orders or whitespace.
Canonical serialisation ensures that these formatting differences do
not produce different payload hashes.

This allows the gateway to classify:

- the same idempotency key and the same payload hash as an expected
  retransmission;
- the same idempotency key and a different payload hash as a
  data-integrity anomaly.

### Relationship to TMA03

This decision implements the payload-hash-based duplicate-control design
described in TMA03. The canonical JSON format and SHA-256 algorithm are
specific implementation choices that were not fixed in the report.

### Final-report action

Explain how canonical JSON and SHA-256 were used to implement payload
comparison, including the distinction between retransmissions and
conflicting message content.


## D004: Ingestion configuration module

Date: 03/08/2026
Status: Accepted

### TMA03 position

TMA03 does not require a dedicated configuration module for the ingestion slice.
Settings such as broker host, port, topic filter, QoS and database paths are not explicitly defined as part of the slice.

### Decision
Introduce an `IngestionConfig` dataclass to hold all settings required by the ingestion slice, including:

MQTT broker host, port, topic filter, QoS and client identifier

keepalive interval

SQLite database path

schema file path

The ingestion service receives an `IngestionConfig` instance and uses it to initialise the MQTT client and open the database.

### Reason
Centralising configuration makes the gateway easier to calibrate during development and testing.
It also prepares the system for later slices where upstream publication, controlled recovery and operational tuning will require additional settings.

Using a dataclass provides immutability, type safety and a clear structure for future configuration fields.

### Relationship to TMA03
This decision extends the implementation beyond the minimum required by TMA03 but does not change the behaviour of the ingestion slice.
It provides an implementation detail that supports maintainability and future extensibility without altering the core design.

### Final‑report action
Describe the configuration module and explain how centralising ingestion settings supports calibration and prepares the gateway for later slices.


## D005: Local MQTT ingestion boundary

Date: 04/08/2026
Status: Accepted

### TMA03 position

The gateway receives technical telemetry through a local Mosquitto
broker, validates each message and commits accepted records to the
SQLite WAL outbox before upstream publication.

### Decision

Use Eclipse Paho to subscribe to `telemetry/#` at QoS 1.

The MQTT callback delegates processing to:

1. `parse_telemetry_message()`
2. `store_message()`

The callback contains no validation rules or SQL logic of its own.

### Reason

Keeping the callback small separates MQTT transport concerns from
message validation and durable persistence. The existing unit-tested
functions remain authoritative for those behaviours.

### Relationship to TMA03

This implements the local ingestion path described in TMA03. The topic
filter, client identifier and Eclipse Paho callback configuration are
implementation details.

### Final-report action

Describe how the local MQTT callback connects the broker to the
validation and SQLite persistence pipeline.
