#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"

PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.expansion_risk_contract_preview_repair \
  --log-dir "$LOG_DIR" \
  --text
