#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MAX_AGE_SECONDS="${MAX_AGE_SECONDS:-180}"
RATE_LIMIT_WINDOW_SECONDS="${RATE_LIMIT_WINDOW_SECONDS:-900}"

echo "R318 REAL TELEGRAM OBSERVATION ALERT SEND GATE PREVIEW"
echo "log_dir: ${LOG_DIR}"
echo "max_age_seconds: ${MAX_AGE_SECONDS}"
echo "rate_limit_window_seconds: ${RATE_LIMIT_WINDOW_SECONDS}"
echo "mode: preview_only"
echo "real_telegram_send: false"
echo "future_confirmation_phrase: ENABLE REAL TELEGRAM OBSERVATION ALERT SEND"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview \
  --log-dir "${LOG_DIR}" \
  --max-age-seconds "${MAX_AGE_SECONDS}" \
  --rate-limit-window-seconds "${RATE_LIMIT_WINDOW_SECONDS}" \
  --text
