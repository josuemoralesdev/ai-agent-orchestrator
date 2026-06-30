#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
TIMEFRAME="${TIMEFRAME:-all}"
LEVERAGE="${LEVERAGE:-all}"

echo "R333BCD ULTRA SHORT BURST LAB IMPLEMENTATION PACK"
echo "log_dir: ${LOG_DIR}"
echo "strategy_family: ULTRA_SHORT_LEVERAGE_BURST"
echo "banner: PAPER ONLY / LIVE PERMISSION FALSE"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_burst_lab_implementation_pack \
  --log-dir "${LOG_DIR}" \
  --timeframe "${TIMEFRAME}" \
  --leverage "${LEVERAGE}" \
  --text \
  --no-write
