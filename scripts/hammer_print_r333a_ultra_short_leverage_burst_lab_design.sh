#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
TIMEFRAME="${TIMEFRAME:-all}"

echo "R333A ULTRA SHORT LEVERAGE BURST LAB DESIGN PACKET"
echo "log_dir: ${LOG_DIR}"
echo "mode: design_only_paper_only_no_live_mutation"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_leverage_burst_lab_design \
  --log-dir "${LOG_DIR}" \
  --timeframe "${TIMEFRAME}" \
  --include-150x \
  --include-visual-spec \
  --include-risk-contract-preview-spec \
  --text \
  --no-write
