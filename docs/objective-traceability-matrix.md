# Objective traceability matrix

Created: 20/07/2026  
Last updated: 31/08/2026

This matrix links the final development and evaluation objectives to the implementation and evidence.

| Objective | Final evidence | Status |
| --------- | -------------- | -------- |
| **DO1** | Telemetry validation, normalised UTC , and local MQTT ingestion have been implemented and tested. | Complete |
| **DO2** | SQLite WAL outbox along with `pending`, `in_flight`, `retry_wait`, and `broker_acknowledged` states have been implemented and tested. | Complete |
| **DO3** | Link-stability checking, QoS 1 health probes, stale `in_flight` recovery, limited recovery, the source ordering, and limited priority have been implemented and tested. | Complete |
| **DO4** | A stable identity, uniqueness constraints, and payload hashing help differentiate expected retransmissions from conflicting content. | Complete |
| **EO1** | Over 15 runs, 1,440 generated messages resulted in 1,440 independent collector observations with no missing messages. | Complete |
| **EO2** | The final dataset showed no duplicate or conflicting collector observations. Duplicate and conflict classification was also confirmed through targeted tests. | Complete |
| **EO3** | The average backlog times to drain was 8.279 seconds for the 30 message outage backlog, 19.496 seconds for the 150 message outage backlog, and 29.755 seconds for the 100 message degraded condition. | Complete |
| **EO4** | Storage samples were collected for 30, 100, and 150 messages backlogs. The majority of observed growth happened in the SQLite WAL. | Complete |
| **EO5** | NetEm was utilised on the Raspberry Pi `wlan0` upstream connection, and the final impairment scenarios were replicated three times. | Complete |

---
