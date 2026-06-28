#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
ADAPTER="${ADAPTER:-all}"
MIN_SAMPLE_COUNT="${MIN_SAMPLE_COUNT:-30}"
PREFERRED_SAMPLE_COUNT="${PREFERRED_SAMPLE_COUNT:-50}"

echo "R328 STRATEGY LAB EVIDENCE ADAPTER IMPLEMENTATION PACK"
echo "log_dir: ${LOG_DIR}"
echo "mode: read_only_diagnostic"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack \
  --log-dir "${LOG_DIR}" \
  --adapter "${ADAPTER}" \
  --min-sample-count "${MIN_SAMPLE_COUNT}" \
  --preferred-sample-count "${PREFERRED_SAMPLE_COUNT}" \
  --text \
  --no-write
