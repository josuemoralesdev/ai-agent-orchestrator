#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/josue/workspace/kernel/ai-agent-orchestrator-main"
UNIT_SOURCE="${REPO_ROOT}/ops/systemd/hammer-paper-refresh.service"
UNIT_TARGET="/etc/systemd/system/hammer-paper-refresh.service"
START_SERVICE=false

if [[ "${1:-}" == "--start" ]]; then
  START_SERVICE=true
elif [[ $# -gt 0 ]]; then
  echo "usage: $0 [--start]" >&2
  exit 2
fi

echo "Installing hammer-paper-refresh.service"
echo "sudo install -m 0644 ${UNIT_SOURCE} ${UNIT_TARGET}"
sudo install -m 0644 "${UNIT_SOURCE}" "${UNIT_TARGET}"

echo "sudo systemctl daemon-reload"
sudo systemctl daemon-reload

echo "sudo systemctl enable hammer-paper-refresh.service"
sudo systemctl enable hammer-paper-refresh.service

if [[ "${START_SERVICE}" == "true" ]]; then
  echo "sudo systemctl start hammer-paper-refresh.service"
  sudo systemctl start hammer-paper-refresh.service
else
  echo "Not starting hammer-paper-refresh.service. Pass --start to start it."
fi
