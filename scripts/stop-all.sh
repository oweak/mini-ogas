#!/bin/bash
# Mini-OGAS — stop all services by port and by process name.

echo "=== 停止所有 Mini-OGAS 服务 ==="

# Kill by port
for port in 8080 8081 8082 8083; do
    pid=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $NF}' | head -1)
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then
        taskkill //F //PID "$pid" 2>/dev/null && echo "  已终止端口 $port (PID $pid)" || true
    fi
done

# Kill agent.py processes
agents=$(tasklist //FI "IMAGENAME eq python.exe" //FO CSV 2>/dev/null | grep "agent" || true)
if [ -n "$agents" ]; then
    taskkill //F //FI "IMAGENAME eq python.exe" 2>/dev/null || true
    echo "  已终止 Python 进程"
fi

echo "完成."
