#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
FEED="${FEED:-all}"
MIN_SAMPLE_COUNT="${MIN_SAMPLE_COUNT:-30}"
PREFERRED_SAMPLE_COUNT="${PREFERRED_SAMPLE_COUNT:-50}"

echo "R326 CANDIDATE FEED EXPANSION FOR STRATEGY LAB VARIANTS"
echo "log_dir: ${LOG_DIR}"
echo "mode: read_only_diagnostic"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion \
  --log-dir "${LOG_DIR}" \
  --feed "${FEED}" \
  --min-sample-count "${MIN_SAMPLE_COUNT}" \
  --preferred-sample-count "${PREFERRED_SAMPLE_COUNT}" \
  --text \
  --no-write
