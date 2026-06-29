#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
ADAPTER="${ADAPTER:-all}"
MIN_READY_ROWS="${MIN_READY_ROWS:-1}"

echo "R329 STRATEGY LAB ADAPTER OUTPUT BATCH EXECUTION PACKET"
echo "log_dir: ${LOG_DIR}"
echo "mode: read_only_diagnostic"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet \
  --log-dir "${LOG_DIR}" \
  --adapter "${ADAPTER}" \
  --min-ready-rows "${MIN_READY_ROWS}" \
  --include-source-data-gaps \
  --include-lab-only \
  --include-watch-only \
  --text \
  --no-write
