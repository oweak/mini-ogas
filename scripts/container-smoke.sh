#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

random_token() {
  python3 -c 'import secrets; print(secrets.token_hex(32))'
}

export COMPOSE_PROJECT_NAME="miniogas-container-gate"
export APP_ENV="digital_twin"
export DATA_SOURCE="simulated"
export CONTROL_MODE="operator_assisted"
export DEMO_SEED_ENABLED="true"
export API_ACCESS_TOKEN="$(random_token)"
export AI_DISPATCHER_TOKEN="$(random_token)"
export NODE_INGEST_TOKEN="$(random_token)"
export JWT_SECRET="$(random_token)"
export AUTH_BOOTSTRAP_PASSWORD="$(random_token)"
export TURNING_NODE_TOKEN="$(random_token)"
export MILLING_NODE_TOKEN="$(random_token)"
export GRINDING_NODE_TOKEN="$(random_token)"
export POSTGRES_PASSWORD="$(random_token)"
export REDIS_PASSWORD="$(random_token)"
export NATS_AUTH_TOKEN="$(random_token)"
export MINIO_ROOT_USER="miniogas-ci"
export MINIO_ROOT_PASSWORD="$(random_token)"
export DEEPSEEK_API_KEY=""
export OGAS_RUN_ID="RUN-CONTAINER-GATE-001"
export OGAS_SCENARIO_ID="SCN-CONTAINER-GATE-001"
export OGAS_SIMULATION_START_TIME="2026-07-16T00:00:00Z"

cd "$ROOT_DIR"

cleanup() {
  status=$?
  if [[ $status -ne 0 ]]; then
    docker compose ps --all || true
    docker compose logs --no-color --tail 200 || true
  fi
  docker compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  return "$status"
}
trap cleanup EXIT

wait_for_url() {
  url="$1"
  for _ in $(seq 1 120); do
    if curl --fail --silent --show-error "$url" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

login() {
  local payload response
  payload=$(printf '{"operator":"admin","password":"%s"}' "$AUTH_BOOTSTRAP_PASSWORD")
  response=$(curl --fail --silent --show-error \
    --header 'Content-Type: application/json' \
    --data "$payload" \
    http://127.0.0.1:8080/api/auth/login)
  printf '%s' "$response" | python3 -c \
    'import json, sys; print(json.load(sys.stdin)["access_token"])'
}

wait_for_ready() {
  for _ in $(seq 1 120); do
    if curl --fail --silent --show-error http://127.0.0.1:8080/health \
      | python3 -c \
        'import json, sys; raise SystemExit(0 if json.load(sys.stdin).get("overall_status") == "ready" else 1)'; then
      return 0
    fi
    sleep 1
  done
  echo "Central API did not reach ready state" >&2
  return 1
}

wait_for_three_nodes() {
  local token="$1"
  for _ in $(seq 1 120); do
    if curl --fail --silent --show-error \
      --header "Authorization: Bearer $token" \
      http://127.0.0.1:8080/api/nodes \
      | python3 -c \
        'import json, sys; expected={"turning-workshop-01","milling-workshop-01","grinding-workshop-01"}; nodes=json.load(sys.stdin); found={n.get("node_code") for n in nodes}; raise SystemExit(0 if expected <= found else 1)'; then
      return 0
    fi
    sleep 1
  done
  echo "Three production nodes did not become observable" >&2
  return 1
}

docker compose config --quiet
docker compose up --build --detach

wait_for_url http://127.0.0.1:8080/health
wait_for_url http://127.0.0.1:8081/health
wait_for_url http://127.0.0.1:8082/health
wait_for_url http://127.0.0.1:8083/health
wait_for_url http://127.0.0.1:8084/health
wait_for_url http://127.0.0.1:5173/
wait_for_url http://127.0.0.1:8222/healthz?js-enabled-only=true
wait_for_url http://127.0.0.1:9000/minio/health/live
wait_for_ready

migration_id=$(docker compose ps --all --quiet migrate)
test -n "$migration_id"
test "$(docker inspect --format '{{.State.ExitCode}}' "$migration_id")" = "0"
docker compose logs --no-color migrate | grep '"backend": "postgresql"'

docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" ping | grep PONG

access_token=$(login)
wait_for_three_nodes "$access_token"

heartbeat_count_before=$(docker compose exec -T postgres \
  psql -U mini_ogas -d mini_ogas -Atc 'SELECT count(*) FROM heartbeat_shadow;')
migration_count_before=$(docker compose exec -T postgres \
  psql -U mini_ogas -d mini_ogas -Atc 'SELECT count(*) FROM schema_migrations;')
test "$heartbeat_count_before" -ge 3
test "$migration_count_before" -gt 0

docker compose stop turning-simpy-node milling-simpy-node grinding-simpy-node
docker compose restart central-api background-worker
wait_for_url http://127.0.0.1:8080/health
wait_for_url http://127.0.0.1:8084/health
wait_for_ready

access_token=$(login)
wait_for_three_nodes "$access_token"
migration_count_after=$(docker compose exec -T postgres \
  psql -U mini_ogas -d mini_ogas -Atc 'SELECT count(*) FROM schema_migrations;')
test "$migration_count_after" = "$migration_count_before"

docker compose start turning-simpy-node milling-simpy-node grinding-simpy-node
for _ in $(seq 1 60); do
  heartbeat_count_after=$(docker compose exec -T postgres \
    psql -U mini_ogas -d mini_ogas -Atc 'SELECT count(*) FROM heartbeat_shadow;')
  if [[ "$heartbeat_count_after" -gt "$heartbeat_count_before" ]]; then
    break
  fi
  sleep 1
done
test "$heartbeat_count_after" -gt "$heartbeat_count_before"
wait_for_three_nodes "$access_token"

for service in postgres redis nats minio central-api background-worker ai-dispatcher \
  market-simulator production-planner dashboard turning-simpy-node milling-simpy-node \
  grinding-simpy-node; do
  container_id=$(docker compose ps --quiet "$service")
  test -n "$container_id"
  test "$(docker inspect --format '{{.State.Running}}' "$container_id")" = "true"
done

for service in postgres redis nats minio central-api background-worker ai-dispatcher \
  market-simulator production-planner dashboard; do
  container_id=$(docker compose ps --quiet "$service")
  test "$(docker inspect --format '{{.State.Health.Status}}' "$container_id")" = "healthy"
done

echo "Container gate passed: full Compose stack, one-shot migration, infrastructure, three nodes, production Dashboard, and restart persistence are verified."
