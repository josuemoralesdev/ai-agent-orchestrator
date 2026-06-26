#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"

echo "R310 MULTI-LANE DRY-RUN OBSERVATION SCHEDULER"
echo "log_dir: ${LOG_DIR}"
echo
echo "PREVIEW"
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler \
  --log-dir "${LOG_DIR}" \
  --preview \
  --text
echo
echo "ONCE"
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler \
  --log-dir "${LOG_DIR}" \
  --once \
  --text
