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
