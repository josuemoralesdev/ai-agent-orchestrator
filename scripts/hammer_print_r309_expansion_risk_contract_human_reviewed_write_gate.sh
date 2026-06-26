#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"

PYTHONPATH=. "$PYTHON_BIN" -m src.app.hammer_radar.operator.expansion_risk_contract_human_reviewed_write_gate \
  --log-dir "$LOG_DIR" \
  --text
