#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MAX_AGE_SECONDS="${MAX_AGE_SECONDS:-180}"
CONFIRMATION="${CONFIRMATION:-SEND MULTI LANE OBSERVATION ALERTS WHEN REQUIRED}"

echo "R317 OBSERVATION ALERT SEND GATE OPERATOR DRILL"
echo "log_dir: ${LOG_DIR}"
echo "max_age_seconds: ${MAX_AGE_SECONDS}"
echo "scenario: all"
echo "telegram_sender_mode: mock"
echo "real_telegram_send: false"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill \
  --log-dir "${LOG_DIR}" \
  --max-age-seconds "${MAX_AGE_SECONDS}" \
  --scenario all \
  --confirmation "${CONFIRMATION}" \
  --text
