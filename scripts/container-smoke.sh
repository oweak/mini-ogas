#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETWORK="miniogas-container-gate"
NODE_TOKEN="container-gate-node-token-0123456789abcdef"
JWT_SECRET="container-gate-jwt-secret-0123456789abcdef"
ADMIN_PASSWORD="container-gate-password"

cd "$ROOT_DIR"

cleanup() {
  status=$?
  if [[ $status -ne 0 ]]; then
    docker logs central-api 2>/dev/null || true
    docker logs node-agent 2>/dev/null || true
    docker logs dashboard 2>/dev/null || true
  fi
  docker rm -f dashboard node-agent central-api >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  return "$status"
}
trap cleanup EXIT

wait_for_url() {
  url="$1"
  container_name="${2:-}"
  for _ in $(seq 1 45); do
    if curl --fail --silent --show-error "$url" >/dev/null; then
      return 0
    fi
    if [[ -n "$container_name" ]] && \
      [[ "$(docker inspect --format '{{.State.Running}}' "$container_name" 2>/dev/null || true)" != true ]]; then
      echo "Container $container_name exited before $url became ready" >&2
      docker inspect "$container_name" --format '{{json .State}}' >&2 || true
      docker logs "$container_name" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

docker build --tag miniogas-central-api:ci services/central-api
docker build --tag miniogas-node-agent:ci services/node-agent
docker build --tag miniogas-dashboard:ci services/dashboard
docker compose --file deploy/docker-compose.central.yml config --quiet

docker network create "$NETWORK" >/dev/null

docker run --detach --name central-api --network "$NETWORK" \
  --publish 18080:8080 \
  --env APP_ENV=digital_twin \
  --env DATA_SOURCE=simulated \
  --env CONTROL_MODE=operator_assisted \
  --env DEMO_SEED_ENABLED=true \
  --env PERSIST_ENABLED=false \
  --env API_ACCESS_TOKEN="$NODE_TOKEN" \
  --env NODE_INGEST_TOKEN="$NODE_TOKEN" \
  --env JWT_SECRET="$JWT_SECRET" \
  --env AUTH_BOOTSTRAP_USERNAME=admin \
  --env AUTH_BOOTSTRAP_PASSWORD="$ADMIN_PASSWORD" \
  --env AI_ENABLED=false \
  --env MICROSERVICES_ENABLED=false \
  --env NATS_ENABLED=false \
  --env REDIS_ENABLED=false \
  --env OBJECT_STORAGE_ENABLED=false \
  miniogas-central-api:ci >/dev/null

wait_for_url http://127.0.0.1:18080/health central-api

docker run --detach --name node-agent --network "$NETWORK" \
  --env CENTRAL_API_URL=http://central-api:8080 \
  --env OGAS_API_TOKEN="$NODE_TOKEN" \
  --env NODE_CODE=milling-workshop-01 \
  --env WORKSHOP_TYPE=milling \
  --env SIMULATION_ENGINE=simpy \
  --env OGAS_RUN_ID=RUN-CONTAINER-GATE-001 \
  --env OGAS_SCENARIO_ID=SCN-CONTAINER-GATE-001 \
  --env HEARTBEAT_SEC=1 \
  miniogas-node-agent:ci >/dev/null

login_payload=$(printf '{"operator":"admin","password":"%s"}' "$ADMIN_PASSWORD")
login_response=$(curl --fail --silent --show-error \
  --header 'Content-Type: application/json' \
  --data "$login_payload" \
  http://127.0.0.1:18080/api/auth/login)
access_token=$(printf '%s' "$login_response" | python3 -c \
  'import json, sys; print(json.load(sys.stdin)["access_token"])')

node_seen=false
for _ in $(seq 1 45); do
  if curl --fail --silent --show-error \
    --header "Authorization: Bearer $access_token" \
    http://127.0.0.1:18080/api/nodes \
    | python3 -c \
      'import json, sys; nodes=json.load(sys.stdin); raise SystemExit(0 if any(n.get("node_code") == "milling-workshop-01" for n in nodes) else 1)'; then
    node_seen=true
    break
  fi
  sleep 1
done

if [[ "$node_seen" != true ]]; then
  echo "Node Agent did not produce an observable heartbeat" >&2
  exit 1
fi

docker run --detach --name dashboard --network "$NETWORK" \
  --publish 15173:5173 \
  miniogas-dashboard:ci >/dev/null

wait_for_url http://127.0.0.1:15173/ dashboard

test "$(docker inspect --format '{{.State.Running}}' central-api)" = true
test "$(docker inspect --format '{{.State.Running}}' node-agent)" = true
test "$(docker inspect --format '{{.State.Running}}' dashboard)" = true

echo "Container gate passed: Central API, Node Agent heartbeat, and production Dashboard are live."
