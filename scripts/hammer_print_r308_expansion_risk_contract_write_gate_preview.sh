#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"

PYTHONPATH=. "$PYTHON_BIN" -m src.app.hammer_radar.operator.expansion_risk_contract_write_gate_preview \
  --log-dir "$LOG_DIR" \
  --text
