#!/bin/bash
# Mini-OGAS one-shot launcher — kills old processes, starts everything fresh, verifies each.
# Run from project root:  bash scripts/start-all.sh

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_TOKEN="${API_ACCESS_TOKEN:-mini-ogas-dev-token}"
export MICROSERVICES_ENABLED=true
export RATE_LIMIT_PER_MINUTE=600

# ---- helpers ----
kill_port() {
    local pid
    pid=$(netstat -ano 2>/dev/null | grep ":$1 " | grep LISTENING | awk '{print $NF}' | head -1)
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then
        taskkill //F //PID "$pid" 2>/dev/null || true
        echo "  已终止端口 $1 (PID $pid)"
    fi
}

wait_health() {
    local url="$1" timeout="${2:-15}" label="${3:-$1}"
    for ((i=0; i<timeout; i++)); do
        if curl -sf "$url" >/dev/null 2>&1; then
            echo "  $label: OK"
            return 0
        fi
        sleep 1
    done
    echo "  $label: FAILED"
    return 1
}

PYTHON="$ROOT/services/central-api/.venv/Scripts/python.exe"

# ================================================================
# Phase 0 — Kill
# ================================================================
# Generate session token for process identity verification
export OGAS_SESSION_TOKEN=$(python -c "import uuid; print(uuid.uuid4())" 2>/dev/null || echo "session-$(date +%s)")
echo "Session token: $OGAS_SESSION_TOKEN"

echo "=== Phase 0: 清理旧进程 ==="
for port in 8080 8081 8082 8083; do
    kill_port $port
done
# Kill any lingering agent.py
taskkill //F //FI "IMAGENAME eq python.exe" 2>/dev/null | grep -i "agent" || true
sleep 1
echo ""

# ================================================================
# Phase 1 — central-api (must be first)
# ================================================================
echo "=== Phase 1: 启动 central-api :8080 ==="
cd "$ROOT/services/central-api"
"$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --log-level warning &
CENTRAL_PID=$!
echo "  PID=$CENTRAL_PID"
wait_health "http://127.0.0.1:8080/preflight" 20 "central-api" || { echo "FATAL: central-api 启动失败"; exit 1; }
echo ""

# ================================================================
# Phase 2 — Microservices
# ================================================================
echo "=== Phase 2: 启动微服务 ==="

start_svc() {
    local name="$1" port="$2" dir="$3"
    echo "  $name :$port ..."
    cd "$dir"
    "$dir/.venv/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port "$port" --log-level warning &
    wait_health "http://127.0.0.1:$port/health" 10 "$name" || echo "  WARNING: $name 未响应"
}

start_svc "ai-dispatcher"      8081 "$ROOT/services/ai-dispatcher"
start_svc "market-simulator"   8082 "$ROOT/services/market-simulator"
start_svc "production-planner" 8083 "$ROOT/services/production-planner"
echo ""

# ================================================================
# Phase 3 — Node agents (real psutil)
# ================================================================
echo "=== Phase 3: 启动节点代理 ==="

declare -A AGENT_PIDS
declare -A AGENT_TYPES

start_agent() {
    local code="$1" wstype="$2"
    echo "  $code ($wstype) ..."
    "$PYTHON" -u "$ROOT/services/node-agent/agent.py" \
        --node-code "$code" \
        --workshop-type "$wstype" \
        --interval 3 \
        --api-url "http://127.0.0.1:8080" \
        --token "$API_TOKEN" &
    AGENT_PIDS["$code"]=$!
    AGENT_TYPES["$code"]="$wstype"
}

start_agent "turning-workshop-01"  "turning"
start_agent "milling-workshop-01"  "milling"
start_agent "grinding-workshop-01" "grinding"
start_agent "cloud-workshop-01"    "cloud"
start_agent "cloud-db-01"          "database"
echo ""

# ================================================================
# Phase 4 — Final verify
# ================================================================
echo "=== Phase 4: 最终验证 ==="
sleep 4

echo "--- 节点状态 ---"
curl -sf -H "X-OGAS-Token: $API_TOKEN" http://127.0.0.1:8080/nodes | \
    python -c "
import sys,json
nodes=json.load(sys.stdin)
online=sum(1 for n in nodes if n['status']=='online')
print(f'  在线: {online}/{len(nodes)}')
for n in nodes:
    print(f'  {n[\"node_code\"]:30s} {n[\"status\"]}')
" 2>/dev/null || echo "  节点查询失败"

echo ""
echo "--- 集成状态 ---"
curl -sf -H "X-OGAS-Token: $API_TOKEN" http://127.0.0.1:8080/management/snapshot | \
    python -c "
import sys,json
s=json.load(sys.stdin)
for i in s.get('integrations',[]):
    print(f'  {i[\"service\"]:25s} {i[\"status\"]}')
" 2>/dev/null || echo "  集成查询失败"

echo ""
echo "========================================="
echo "  控制台: http://127.0.0.1:8080"
echo "  API文档: http://127.0.0.1:8080/docs"
echo "  停止所有: bash scripts/stop-all.sh"
echo "========================================="

# ================================================================
# Phase 5 — Watchdog: auto-restart crashed agents
# ================================================================
echo ""
echo "=== Phase 5: Watchdog active (Ctrl+C to stop all) ==="
echo "  Agent processes are monitored every 5 seconds."
echo "  Crashed agents will be auto-restarted."

while true; do
    sleep 5
    for code in "${!AGENT_PIDS[@]}"; do
        pid="${AGENT_PIDS[$code]}"
        wstype="${AGENT_TYPES[$code]}"
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "$(date +%H:%M:%S) Watchdog: $code (PID $pid) crashed, restarting..."
            "$PYTHON" -u "$ROOT/services/node-agent/agent.py" \
                --node-code "$code" \
                --workshop-type "$wstype" \
                --interval 3 \
                --api-url "http://127.0.0.1:8080" \
                --token "$API_TOKEN" &
            AGENT_PIDS["$code"]=$!
            echo "$(date +%H:%M:%S) Watchdog: $code restarted (new PID ${AGENT_PIDS[$code]})"
        fi
    done
done
