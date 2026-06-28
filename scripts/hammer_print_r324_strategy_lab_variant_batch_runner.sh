#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
BATCH="${BATCH:-all}"
MIN_SAMPLE_COUNT="${MIN_SAMPLE_COUNT:-30}"
PREFERRED_SAMPLE_COUNT="${PREFERRED_SAMPLE_COUNT:-50}"
STANDARD_MIN_WIN_RATE_PCT="${STANDARD_MIN_WIN_RATE_PCT:-55}"
BETRAYAL_MIN_WIN_RATE_PCT="${BETRAYAL_MIN_WIN_RATE_PCT:-60}"

echo "R324 STRATEGY LAB VARIANT BATCH RUNNER"
echo "log_dir: ${LOG_DIR}"
echo "batch: ${BATCH}"
echo "mode: read_only_diagnostic"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_variant_batch_runner \
  --log-dir "${LOG_DIR}" \
  --batch "${BATCH}" \
  --min-sample-count "${MIN_SAMPLE_COUNT}" \
  --preferred-sample-count "${PREFERRED_SAMPLE_COUNT}" \
  --standard-min-win-rate-pct "${STANDARD_MIN_WIN_RATE_PCT}" \
  --betrayal-min-win-rate-pct "${BETRAYAL_MIN_WIN_RATE_PCT}" \
  --text \
  --no-write
