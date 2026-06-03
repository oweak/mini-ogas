-- Central PostgreSQL schema draft.

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL
);

CREATE TABLE IF NOT EXISTS permissions (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(128) NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT ''
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
    severity VARCHAR(32) NOT NULL,
    root_cause TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    need_isolation BOOLEAN NOT NULL DEFAULT false,
    model_name VARCHAR(64) NOT NULL DEFAULT 'deepseek',
    raw_response JSONB,
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
    detail JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

