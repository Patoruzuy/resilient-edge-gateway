# Design decision log

This log records decisions that affect the design or evaluation of the local-first edge gateway. Coding corrections are recorded in the implementation progress log.

## D001: SQLite WAL outbox schema

Date: 25/07/2026  
Status: Accepted

### Decision

Use one `outbox_messages` table as the record for accepted telemetry and delivery state. The states are:

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

Use configuration dataclasses for broker settings, QoS, timeouts and database paths.

### Reason

Centralised configuration makes local testing easier and allows later controlled recovery settings to be changed without altering the main processing logic.

### Relationship to TMA03

This is an implementation detail. It does not change the TMA03 architecture.

---

## D005: Local MQTT ingestion boundary

Date: 04/08/2026  
Status: Accepted

### Decision

Use Eclipse Paho to subscribe to the local Mosquitto broker at QoS 1. The MQTT callback passes the incoming publication to the existing validation and repository functions.

### Reason

Keeping the callback small separates MQTT handling from validation and local persistence. This makes the ingestion path easier to test and keeps the SQLite WAL commit as the durability boundary.

### Relationship to TMA03

This implements the local ingestion path described in TMA03:

`publisher  -> local broker  -> local-first edge gateway  -> local persistence`

---

## D006: Upstream publication and acknowledgement handling

Date: 09/08/2026  
Status: Accepted

### Decision

Publish one eligible `pending` outbox record at a time to the upstream broker using MQTT QoS 1.

Before publication:

`pending  -> in_flight`

After confirmed broker acknowledgement:

`in_flight  -> broker_acknowledged`

If publication fails or acknowledgement cannot be confirmed:

`in_flight  -> retry_wait`

Pending records are selected in a deterministic order using source timestamp and row identifier.

### Reason

This implements the acknowledgement state model without introducing uncontrolled backlog replay. limited replay and link-stability checks belong to the later controlled recovery slice.

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

---

## D008: Persistent duplicate-control evidence

Date: 14/08/2026
Status: Accepted

### Decision

Keep the existing idempotency rule:

`device_id + publisher_session_id + source_sequence`

The existing payload hash is used to distinguish:

- the same identity and same content as an expected retransmission;
- the same identity and different content as a data-integrity anomaly.

Neither case creates another outbox row.

A small SQLite table records these duplicate-control events so that
the results can be counted during later evaluation.

The evaluation collector continues to retain all upstream observations,
including repeated arrivals.

### Reason

TMA03 requires repeated messages and conflicting records to be
distinguished using stable identifiers and SQLite uniqueness.

Persisting the classification provides evidence for EO2 without changing
the existing outbox design.

### Limitation

This slice confirms that duplicate control can be measured. It does not
yet evaluate duplicates produced during controlled recovery.

---

## D009: Stale `in_flight` recovery

Date: 17/08/2026  
Status: Accepted

### Decision

Treat an `in_flight` record as stale when its last attempt is older than
the configured timeout.

At startup, stale records are changed atomically:

`in_flight` to `retry_wait`

This recovery step does not increase `attempt_count`.

### Reason

The gateway may stop after an upstream publication has started but
before the broker acknowledgement is stored in SQLite. Without recovery,
the record could remain stranded in `in_flight`.

Moving it to `retry_wait` keeps the earlier attempt visible and makes the
message eligible for controlled recovery.

### Limitation

The upstream broker may already have accepted the earlier publication.
A later retry can create a repeated delivery. This is expected
under at-least-once recovery and is measured through the duplicate
evidence rather than hidden.

---

## D010: Link-stability gate and limited recovery

Date: 19/08/2026  
Status: Accepted

### Decision

Controlled recovery starts only after the upstream MQTT connection has
remained active for the configured stability period and a QoS 1 health
publication on `gateway/health` has been acknowledged.

`pending` and `retry_wait` records are then released in limited batches.

A full stability period is needed when recovery starts or after a
publication or health check fails. Between successful batches, the
gateway uses the configured pause and another health publication rather
than repeating the complete stability delay.

Source sequence is preserved within each device and publisher session.
Limited priority positions allow priority to influence replay without
indefinitely starving older backlog.

### Reason

A short MQTT reconnection may fail again immediately. The stability gate
and health acknowledgement give recovery a simple entry condition, while
limited batches prevent the complete backlog from being released as one
burst.

Repeating the complete stability delay after every successful batch was
not used because it would add artificial delay to backlog drain time.

### Limitation

The selected stability period, batch size, pause and priority policy can
affect recovery time. They are implementation settings, not claimed to
be optimal, and will be examined during impairment-based evaluation.

---

## D011: impairment-based evaluation method

Date: 22/08/2026  
Status: Accepted

### Decision

Use five scenarios with three runs of each:

- direct publication baseline;
- gateway baseline;
- 100 ms delay with 10% configured loss;
- 15-second outage at 2 messages/s;
- 30-second outage at 5 messages/s.

`evaluation/scenarios.json` is the source for the numerical parameters.
Each run uses a unique evidence directory and gateway tests start from a clean database state.

NetEm is applied only to the upstream path. Direct runs reconcile the publisher with the evaluation collector, while gateway runs reconcile publisher, gateway and collector evidence.

For outage runs, actual impairment duration is recorded separately from backlog drain time. Backlog drain time is measured from `recovery_started` to `recovery_complete`.

### Reason

This gives EO1 to EO5 a repeatable comparison while keeping the
evaluation small enough to complete and explain. Clean run isolation and recorded timing reduce the risk of mixing evidence from different tests.

### Limitation

Three repetitions support descriptive comparison rather than strong statistical claims. Storage measurements are sampled application-level indicators, not direct measurements of physical SD-card writes.

The outage tests recover the complete backlog after the publisher finishes. They do not claim to evaluate continuous forwarding while recovery is already draining the backlog.

---

## D012: Physical impairment-evaluation topology

Date: 30/08/2026
Status: Accepted

### Decision

Use the Raspberry Pi for the local gateway and the Windows PC for the upstream broker.

The final path is:

`publisher -> local broker  -> gateway  -> wlan0  -> Windows upstream broker`

NetEm is applied only to `wlan0`. The local broker remains on `localhost:1883`.

### Reason

Earlier same-host testing did not send upstream traffic through the impaired interface. The physical Pi-to-Windows path ensures that NetEm affects upstream communication without affecting local ingestion.

### Limitation

The evaluation represents controlled LAN impairment rather than a real wide-area network.

---

## D013: Runs frozen evaluation evidence

Date: 31/08/2026
Status: Accepted

### Decision

Store the live Windows collector database outside synchronised folders while a run is active.

After collector shutdown:

1. copy `evaluation.db` into the run evidence directory;
2. copy the corresponding gateway database;
3. reconcile using the frozen copies;
4. keep failed or anomalous runs unchanged.

### Reason

Live SQLite collection was less reliable inside a synchronised directory. A later audit also showed that successful runtime behaviour does not guarantee that the archived database contains the correct run evidence.

Freezing and rechecking each run makes the final dataset reproducible.

### Limitation

Runs with incomplete or inconsistent frozen evidence remain part of the project record but are excluded from the dataset.

---
