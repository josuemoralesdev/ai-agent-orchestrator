#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MAX_AGE_SECONDS="${MAX_AGE_SECONDS:-180}"
RATE_LIMIT_WINDOW_SECONDS="${RATE_LIMIT_WINDOW_SECONDS:-900}"
SCENARIO="${SCENARIO:-synthetic_stale_observation}"

echo "R322 OPERATOR-RUN REAL TELEGRAM SYNTHETIC ALERT SEND ACTIVATION PACKET"
echo "log_dir: ${LOG_DIR}"
echo "max_age_seconds: ${MAX_AGE_SECONDS}"
echo "rate_limit_window_seconds: ${RATE_LIMIT_WINDOW_SECONDS}"
echo "scenario: ${SCENARIO}"
echo "mode: activation_packet_only"
echo "real_telegram_send: false"
echo "manual_real_send: not_available_in_current_code"
echo "confirmation_phrase_required: ENABLE REAL TELEGRAM OBSERVATION ALERT SEND"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_activation_packet \
  --log-dir "${LOG_DIR}" \
  --max-age-seconds "${MAX_AGE_SECONDS}" \
  --rate-limit-window-seconds "${RATE_LIMIT_WINDOW_SECONDS}" \
  --scenario "${SCENARIO}" \
  --text
