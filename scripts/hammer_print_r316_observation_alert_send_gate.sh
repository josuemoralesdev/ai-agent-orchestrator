#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MAX_AGE_SECONDS="${MAX_AGE_SECONDS:-180}"
RATE_LIMIT_WINDOW_SECONDS="${RATE_LIMIT_WINDOW_SECONDS:-900}"

echo "R316 HUMAN-REVIEWED OBSERVATION ALERT SEND GATE"
echo "log_dir: ${LOG_DIR}"
echo "max_age_seconds: ${MAX_AGE_SECONDS}"
echo "rate_limit_window_seconds: ${RATE_LIMIT_WINDOW_SECONDS}"
echo "mode: preview_only"
echo "telegram_sender_mode: mock"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate \
  --log-dir "${LOG_DIR}" \
  --max-age-seconds "${MAX_AGE_SECONDS}" \
  --rate-limit-window-seconds "${RATE_LIMIT_WINDOW_SECONDS}" \
  --telegram-sender-mode mock \
  --text
