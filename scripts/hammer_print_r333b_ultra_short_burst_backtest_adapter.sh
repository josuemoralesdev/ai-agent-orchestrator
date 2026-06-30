#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
TIMEFRAME="${TIMEFRAME:-all}"
LEVERAGE="${LEVERAGE:-all}"

echo "R333B ULTRA SHORT BURST BACKTEST ADAPTER"
echo "log_dir: ${LOG_DIR}"
echo "mode: paper_only_replay_adapter_live_false"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_burst_backtest_adapter \
  --log-dir "${LOG_DIR}" \
  --timeframe "${TIMEFRAME}" \
  --leverage "${LEVERAGE}" \
  --text \
  --no-write
