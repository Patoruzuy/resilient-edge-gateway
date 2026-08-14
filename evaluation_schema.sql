PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS collector_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    run_id TEXT NOT NULL,

    received_at TEXT NOT NULL,
    topic TEXT NOT NULL,

    qos INTEGER NOT NULL,
    retained INTEGER NOT NULL DEFAULT 0,
    mqtt_duplicate INTEGER NOT NULL DEFAULT 0,

    message_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    publisher_session_id TEXT NOT NULL,
    source_sequence INTEGER NOT NULL,
    source_timestamp TEXT NOT NULL,
    priority INTEGER NOT NULL,

    payload TEXT NOT NULL,
    payload_hash TEXT NOT NULL,

    raw_message BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_collector_run
    ON collector_observations(run_id);

CREATE INDEX IF NOT EXISTS idx_collector_message_id
    ON collector_observations(
        run_id,
        message_id
    );

CREATE INDEX IF NOT EXISTS idx_collector_identity
    ON collector_observations(
        run_id,
        device_id,
        publisher_session_id,
        source_sequence
    );


CREATE TABLE IF NOT EXISTS collector_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    run_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    topic TEXT NOT NULL,

    qos INTEGER NOT NULL,
    retained INTEGER NOT NULL DEFAULT 0,
    mqtt_duplicate INTEGER NOT NULL DEFAULT 0,

    reason_code TEXT NOT NULL,
    detail TEXT,

    raw_message BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_collector_rejections_run
    ON collector_rejections(run_id);
