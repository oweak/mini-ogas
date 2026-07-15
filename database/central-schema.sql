-- Central PostgreSQL schema draft.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
    name VARCHAR(64) PRIMARY KEY,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS permissions (
    name VARCHAR(128) PRIMARY KEY,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS user_roles (
    username VARCHAR(64) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    role_name VARCHAR(64) NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
    PRIMARY KEY (username, role_name)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_name VARCHAR(64) NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
    permission_name VARCHAR(128) NOT NULL REFERENCES permissions(name) ON DELETE CASCADE,
    PRIMARY KEY (role_name, permission_name)
);

CREATE TABLE IF NOT EXISTS nodes (
    id BIGSERIAL PRIMARY KEY,
    node_code VARCHAR(64) NOT NULL UNIQUE,
    node_name VARCHAR(128) NOT NULL,
    workshop_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'offline',
    last_heartbeat TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS metrics (
    id BIGSERIAL PRIMARY KEY,
    node_code VARCHAR(64) NOT NULL,
    cpu_usage NUMERIC(5, 2) NOT NULL,
    memory_usage NUMERIC(5, 2) NOT NULL,
    disk_usage NUMERIC(5, 2) NOT NULL,
    network_in BIGINT NOT NULL,
    network_out BIGINT NOT NULL,
    db_latency_ms INTEGER NOT NULL,
    api_latency_ms INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    node_code VARCHAR(64) NOT NULL,
    alert_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    source VARCHAR(32) NOT NULL,
    description TEXT NOT NULL,
    handled_by VARCHAR(32),
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ai_diagnosis (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT,
    severity VARCHAR(32) NOT NULL DEFAULT 'medium',
    node_code VARCHAR(64),
    root_cause TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    confidence NUMERIC(6, 4) NOT NULL DEFAULT 0.0,
    need_isolation BOOLEAN NOT NULL DEFAULT false,
    model_name VARCHAR(64) NOT NULL DEFAULT 'deepseek',
    raw_response TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS production_orders (
    id BIGSERIAL PRIMARY KEY,
    product_code VARCHAR(64) NOT NULL,
    process_route TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    deadline TIMESTAMPTZ,
    market_source VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS production_records (
    id BIGSERIAL PRIMARY KEY,
    node_code VARCHAR(64) NOT NULL,
    workshop_type VARCHAR(32) NOT NULL,
    machine_code VARCHAR(64) NOT NULL,
    order_id BIGINT,
    process_type VARCHAR(32) NOT NULL,
    planned_quantity INTEGER NOT NULL,
    finished_quantity INTEGER NOT NULL,
    defect_quantity INTEGER NOT NULL,
    energy_used NUMERIC(12, 2) NOT NULL,
    tool_wear_level NUMERIC(5, 2) NOT NULL,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS market_demand (
    id BIGSERIAL PRIMARY KEY,
    product_code VARCHAR(64) NOT NULL,
    current_price NUMERIC(12, 2) NOT NULL,
    competitor_price NUMERIC(12, 2) NOT NULL,
    demand_index NUMERIC(8, 2) NOT NULL,
    season_factor NUMERIC(8, 2) NOT NULL,
    inventory_pressure NUMERIC(8, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hostile_events (
    id BIGSERIAL PRIMARY KEY,
    node_code VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    source_ip VARCHAR(64),
    action_taken VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor VARCHAR(64) NOT NULL,
    action VARCHAR(128) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id VARCHAR(128) NOT NULL,
    result VARCHAR(32) NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_store (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_node TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    ingest_time TIMESTAMPTZ NOT NULL,
    local_sequence BIGINT NOT NULL,
    global_sequence BIGINT NOT NULL UNIQUE,
    correlation_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_store_run_global ON event_store(run_id, global_sequence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_store_source_local
    ON event_store(source_node, run_id, local_sequence);

CREATE TABLE IF NOT EXISTS part_queue_shadow (
    part_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    scenario_id TEXT NOT NULL DEFAULT '',
    batch_id TEXT NOT NULL DEFAULT '',
    parent_part_id TEXT NOT NULL DEFAULT '',
    order_id TEXT NOT NULL,
    product_code TEXT NOT NULL DEFAULT '',
    current_step TEXT NOT NULL,
    current_operation TEXT NOT NULL DEFAULT '',
    next_operation TEXT NOT NULL DEFAULT '',
    quality_status TEXT NOT NULL DEFAULT 'pending',
    event_sequence BIGINT NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    claimed_by TEXT NOT NULL DEFAULT '',
    claim_token TEXT NOT NULL DEFAULT '',
    claim_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS command_shadow (
    command_id BIGINT PRIMARY KEY,
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    claimed_by TEXT NOT NULL DEFAULT '',
    result_message TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    expires_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'not_started',
    verification_baseline_json TEXT NOT NULL DEFAULT '{}',
    verification_evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS heartbeat_shadow (
    id BIGSERIAL PRIMARY KEY,
    node_code TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    scenario_id TEXT NOT NULL DEFAULT '',
    simulation_time TIMESTAMPTZ,
    payload_json TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_shadow_node_received
    ON heartbeat_shadow(node_code, received_at);

CREATE TABLE IF NOT EXISTS node_record_receipts (
    node_code TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    local_id BIGINT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_created_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (node_code, run_id, local_id)
);

CREATE TABLE IF NOT EXISTS nats_shadow_receipts (
    message_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    message_type TEXT NOT NULL,
    source_node TEXT NOT NULL,
    run_id TEXT NOT NULL,
    local_sequence BIGINT NOT NULL,
    correlation_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nats_shadow_source_run_sequence
    ON nats_shadow_receipts(source_node, run_id, local_sequence);
