#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
TIMEFRAME="${TIMEFRAME:-all}"
LEVERAGE="${LEVERAGE:-all}"

echo "R333C ULTRA SHORT BURST VISUAL TERMINAL PANEL"
echo "log_dir: ${LOG_DIR}"
echo "mode: terminal_only_no_hosted_ui_live_false"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_burst_visual_terminal_panel \
  --log-dir "${LOG_DIR}" \
  --timeframe "${TIMEFRAME}" \
  --leverage "${LEVERAGE}" \
  --text \
  --no-write
