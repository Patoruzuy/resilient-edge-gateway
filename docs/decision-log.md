# Design decision log

This log records decisions that affect the design or evaluation of the local-first edge gateway. Routine coding corrections are recorded in the implementation progress log instead.

## D001: SQLite WAL outbox schema

Date: 25/07/2026  
Status: Accepted

### Decision

Use one `outbox_messages` table as the durable record for accepted telemetry and delivery state. The durable states are:

- `pending`
- `in_flight`
- `retry_wait`
- `broker_acknowledged`

The idempotency key is:

`device_id + publisher_session_id + source_sequence`

The table also records publication attempts and timing fields needed for later recovery and evaluation.

### Reason

A single outbox table keeps local persistence and delivery state easy to inspect. SQLite WAL provides a simple persistence mechanism suitable for the Raspberry Pi target while supporting the later measurement of backlog drain time and storage behaviour.

### Relationship to TMA03

This follows the TMA03 outbox design. The timing and retry fields are implementation details that support controlled recovery and evaluation.

---

## D002: Telemetry message contract

Date: 26/07/2026  
Status: Accepted

### Decision

Use the following telemetry fields:

- `message_id`
- `device_id`
- `publisher_session_id`
- `source_sequence`
- `source_timestamp`
- `priority`
- `payload`

The MQTT topic remains part of the MQTT message envelope and is stored separately when the gateway receives the publication.

### Reason

This keeps the message contract close to the structure described in TMA03 and avoids adding fields that are already supplied by MQTT.

### Relationship to TMA03

The decision is consistent with the submitted message structure and supports later reconciliation between publisher, gateway and collector evidence.

---

## D003: Canonical payload hashing

Date: 29/07/2026  
Status: Accepted

### Decision

Serialise payloads in a consistent JSON form and calculate a SHA-256 hash from that representation.

The gateway classifies:

- the same idempotency key with the same payload hash as an expected retransmission duplicate;
- the same idempotency key with a different payload hash as a data-integrity anomaly.

### Reason

Equivalent JSON can differ in whitespace or key order. Canonical handling prevents these formatting differences from being treated as different telemetry content.

### Relationship to TMA03

This implements the duplicate-control approach described in TMA03. SHA-256 and the exact JSON format are implementation choices.

---

## D004: Centralised gateway configuration

Date: 03/08/2026  
Status: Accepted

### Decision

Use configuration dataclasses for broker settings, QoS, timeouts and database paths rather than spreading these values through the gateway code.

### Reason

Centralised configuration makes local testing easier and allows later controlled recovery settings to be changed without altering the main processing logic.

### Relationship to TMA03

This is an implementation detail. It does not change the TMA03 architecture.

---

## D005: Local MQTT ingestion boundary

Date: 04/08/2026  
Status: Accepted

### Decision

Use Eclipse Paho to subscribe to the local Mosquitto broker at QoS 1. The MQTT callback passes the incoming publication to the existing validation and repository functions rather than implementing validation or SQL itself.

### Reason

Keeping the callback small separates MQTT handling from validation and local persistence. This makes the ingestion path easier to test and keeps the SQLite WAL commit as the durability boundary.

### Relationship to TMA03

This implements the local ingestion path described in TMA03:

`publisher → local broker → local-first edge gateway → local persistence`

---

## D006: Upstream publication and acknowledgement handling

Date: 09/08/2026  
Status: Accepted

### Decision

Publish one eligible `pending` outbox record at a time to the upstream broker using MQTT QoS 1.

Before publication:

`pending → in_flight`

After confirmed broker acknowledgement:

`in_flight → broker_acknowledged`

If publication fails or acknowledgement cannot be confirmed:

`in_flight → retry_wait`

Pending records are selected in a deterministic order using source timestamp and row identifier.

### Reason

This implements the durable acknowledgement state model without introducing uncontrolled backlog replay. Bounded replay and link-stability checks belong to the later controlled recovery slice.

An acknowledgement timeout is treated as uncertainty rather than proof that the upstream broker did not receive the message. This keeps the design consistent with at-least-once recovery behaviour and allows any later duplicate to be measured.

### Relationship to TMA03

The state transitions follow TMA03. This decision does not claim that controlled recovery has been implemented.

### Limitation

`broker_acknowledged` is broker-level evidence only. It is kept separate from independent collector observation.

---

## D007: Independent evaluation evidence with shared persistence modules

Date: 10/08/2026  
Status: Accepted

### Decision

Use a separate MQTT evaluation collector subscribed to the upstream broker.

Store collector evidence in:

`data/evaluation.db`

Keep gateway operational state in:

`data/gateway.db`

The two databases use separate SQL schemas but share the existing Python database and repository modules. This avoids creating extra persistence modules that do not add value to the project.

Each collector observation records the evaluation run, receipt timestamp, MQTT metadata, telemetry identity, payload and payload hash. Repeated observations are retained as separate rows.

### Reason

The collector should record what was independently observed rather than use gateway state as evidence of its own success. Keeping the physical databases separate maintains that distinction, while sharing the Python modules keeps the implementation manageable.

Repeated observations are not removed because duplicate arrival is part of EO2.

`payload_hash` remains derived evidence rather than part of the incoming telemetry contract. The collector uses the same canonical payload-hash method as the gateway so that records can be reconciled consistently.

### Relationship to TMA03

This implements the independent collector required for delivery completeness and duplicate control. The separate evaluation database, run identifier and shared Python persistence modules are implementation choices that support repeatability without changing the submitted architecture.

### Limitation

Collector observation confirms arrival at the evaluation subscriber. It does not explain why a message was duplicated or lost. Those behaviours will be examined in the later duplicate-control and impairment-based evaluation work.
