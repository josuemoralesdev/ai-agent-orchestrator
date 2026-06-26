#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"

echo "R311 MULTI-LANE DRY-RUN TIMER UNIT PREVIEW"
echo "log_dir: ${LOG_DIR}"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_unit_preview \
  --log-dir "${LOG_DIR}" \
  --no-write \
  --text
echo
echo "R311 is preview only."
echo "No systemd files are installed, enabled, started, stopped, or reloaded by this script."
echo "Recommended R312 path: R312 Human-Reviewed Multi-Lane Timer Install Gate if this preview remains clean."
