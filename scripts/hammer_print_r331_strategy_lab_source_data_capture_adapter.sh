#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
ADAPTER="${ADAPTER:-all}"
MAX_SOURCE_ROWS="${MAX_SOURCE_ROWS:-500}"

echo "R331 STRATEGY LAB SOURCE DATA CAPTURE ADAPTER"
echo "log_dir: ${LOG_DIR}"
echo "mode: read_only_source_ledger_only"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter \
  --log-dir "${LOG_DIR}" \
  --adapter "${ADAPTER}" \
  --include-lab-only \
  --include-watch-only \
  --max-source-rows "${MAX_SOURCE_ROWS}" \
  --text \
  --no-write
