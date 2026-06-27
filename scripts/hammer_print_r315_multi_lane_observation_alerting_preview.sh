#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MAX_AGE_SECONDS="${MAX_AGE_SECONDS:-180}"

echo "R315 MULTI-LANE OBSERVATION ALERTING PREVIEW"
echo "log_dir: ${LOG_DIR}"
echo "max_age_seconds: ${MAX_AGE_SECONDS}"
echo "telegram_send: preview_only_false"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_alerting_preview \
  --log-dir "${LOG_DIR}" \
  --max-age-seconds "${MAX_AGE_SECONDS}" \
  --text
