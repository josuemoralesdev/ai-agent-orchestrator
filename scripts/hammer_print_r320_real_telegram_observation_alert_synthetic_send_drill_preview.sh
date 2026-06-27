#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MAX_AGE_SECONDS="${MAX_AGE_SECONDS:-180}"
RATE_LIMIT_WINDOW_SECONDS="${RATE_LIMIT_WINDOW_SECONDS:-900}"
SCENARIO="${SCENARIO:-all}"

echo "R320 REAL TELEGRAM OBSERVATION ALERT SYNTHETIC SEND DRILL PREVIEW"
echo "log_dir: ${LOG_DIR}"
echo "max_age_seconds: ${MAX_AGE_SECONDS}"
echo "rate_limit_window_seconds: ${RATE_LIMIT_WINDOW_SECONDS}"
echo "scenario: ${SCENARIO}"
echo "mode: preview_only"
echo "real_telegram_send: false"
echo "future_confirmation_phrase: ENABLE REAL TELEGRAM OBSERVATION ALERT SEND"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_synthetic_send_drill_preview \
  --log-dir "${LOG_DIR}" \
  --max-age-seconds "${MAX_AGE_SECONDS}" \
  --rate-limit-window-seconds "${RATE_LIMIT_WINDOW_SECONDS}" \
  --scenario "${SCENARIO}" \
  --text
