#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
ADAPTER="${ADAPTER:-all}"
MAX_ROWS="${MAX_ROWS:-1000}"

echo "R332 STRATEGY LAB CAPTURED SOURCE DATA MERGE INTO ADAPTER ROWS"
echo "log_dir: ${LOG_DIR}"
echo "mode: read_only_merge_packet"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_captured_source_data_merge \
  --log-dir "${LOG_DIR}" \
  --adapter "${ADAPTER}" \
  --include-lab-only \
  --include-watch-only \
  --include-pending \
  --max-rows "${MAX_ROWS}" \
  --text \
  --no-write
