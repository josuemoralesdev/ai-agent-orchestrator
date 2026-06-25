#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"

PYTHONPATH=. "$PYTHON_BIN" -m src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview \
  --log-dir "$LOG_DIR" \
  --text
