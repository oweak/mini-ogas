-- Local SQLite schema draft for a workshop node.

CREATE TABLE IF NOT EXISTS local_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT NOT NULL,
    cpu_usage REAL NOT NULL,
    memory_usage REAL NOT NULL,
    disk_usage REAL NOT NULL,
    network_in INTEGER NOT NULL,
    network_out INTEGER NOT NULL,
    db_latency_ms INTEGER NOT NULL,
    api_latency_ms INTEGER NOT NULL,
    synced INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_production_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT NOT NULL,
    workshop_type TEXT NOT NULL,
    machine_code TEXT NOT NULL,
    order_code TEXT NOT NULL,
    process_type TEXT NOT NULL,
    planned_quantity INTEGER NOT NULL,
    finished_quantity INTEGER NOT NULL,
    defect_quantity INTEGER NOT NULL,
    energy_used REAL NOT NULL,
    tool_wear_level REAL NOT NULL,
    synced INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    synced INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id TEXT NOT NULL UNIQUE,
    command_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS sync_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_metrics_id INTEGER NOT NULL DEFAULT 0,
    last_production_id INTEGER NOT NULL DEFAULT 0,
    last_alert_id INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

