#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MIN_SAMPLE_COUNT="${MIN_SAMPLE_COUNT:-30}"
PREFERRED_SAMPLE_COUNT="${PREFERRED_SAMPLE_COUNT:-50}"
STANDARD_MIN_WIN_RATE_PCT="${STANDARD_MIN_WIN_RATE_PCT:-55}"
BETRAYAL_MIN_WIN_RATE_PCT="${BETRAYAL_MIN_WIN_RATE_PCT:-60}"

echo "R325 STRATEGY LAB PROMOTION REVIEW PACKET"
echo "log_dir: ${LOG_DIR}"
echo "mode: read_only_diagnostic"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_promotion_review_packet \
  --log-dir "${LOG_DIR}" \
  --min-sample-count "${MIN_SAMPLE_COUNT}" \
  --preferred-sample-count "${PREFERRED_SAMPLE_COUNT}" \
  --standard-min-win-rate-pct "${STANDARD_MIN_WIN_RATE_PCT}" \
  --betrayal-min-win-rate-pct "${BETRAYAL_MIN_WIN_RATE_PCT}" \
  --text \
  --no-write
