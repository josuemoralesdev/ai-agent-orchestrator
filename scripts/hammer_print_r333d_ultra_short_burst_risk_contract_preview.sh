#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
TIMEFRAME="${TIMEFRAME:-all}"
LEVERAGE="${LEVERAGE:-all}"

echo "R333D ULTRA SHORT BURST RISK CONTRACT PREVIEW"
echo "log_dir: ${LOG_DIR}"
echo "mode: preview_only_no_config_write_live_false"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_burst_risk_contract_preview \
  --log-dir "${LOG_DIR}" \
  --timeframe "${TIMEFRAME}" \
  --leverage "${LEVERAGE}" \
  --include-150x \
  --text \
  --no-write
