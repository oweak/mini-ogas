#!/usr/bin/env bash
set -euo pipefail

APP_USER="miniogas"
APP_ROOT="/opt/mini-ogas"
DATA_ROOT="/var/lib/mini-ogas"
ENV_ROOT="/etc/mini-ogas"

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --home "${APP_ROOT}" --shell /usr/sbin/nologin "${APP_USER}"
fi

install -d -m 0755 "${APP_ROOT}/node-agent" "${APP_ROOT}/scripts" "${DATA_ROOT}" "${ENV_ROOT}"
install -m 0755 node-agent "${APP_ROOT}/node-agent/node-agent"

if [ -d scripts ]; then
  cp -R scripts/. "${APP_ROOT}/scripts/"
fi

if [ ! -f "${ENV_ROOT}/node-agent.env" ]; then
  install -m 0644 node-agent.env.example "${ENV_ROOT}/node-agent.env"
fi

chown -R "${APP_USER}:${APP_USER}" "${APP_ROOT}" "${DATA_ROOT}"
install -m 0644 mini-ogas-node-agent.service /etc/systemd/system/mini-ogas-node-agent.service

systemctl daemon-reload
systemctl enable mini-ogas-node-agent
systemctl restart mini-ogas-node-agent

echo "Mini-OGAS node-agent installed."
echo "Edit ${ENV_ROOT}/node-agent.env if needed, then run:"
echo "  sudo systemctl restart mini-ogas-node-agent"
echo "  sudo journalctl -u mini-ogas-node-agent -f"
