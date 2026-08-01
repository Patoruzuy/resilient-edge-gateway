PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS outbox_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    device_id TEXT NOT NULL,
    publisher_session_id TEXT NOT NULL,
    source_sequence INTEGER NOT NULL,
    source_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    delivery_state TEXT NOT NULL
        CHECK (
            delivery_state IN (
                'pending',
                'in_flight',
                'retry_wait',
                'broker_acknowledged'
            )
        ),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    acknowledged_at TEXT,
    next_retry_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE (
        device_id,
        publisher_session_id,
        source_sequence
    )
);