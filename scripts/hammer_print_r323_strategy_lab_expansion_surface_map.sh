#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MAX_OBSERVATION_AGE_SECONDS="${MAX_OBSERVATION_AGE_SECONDS:-300}"

echo "R323 STRATEGY LAB EXPANSION RE-ENTRY AND CANDIDATE SURFACE MAP"
echo "log_dir: ${LOG_DIR}"
echo "max_observation_age_seconds: ${MAX_OBSERVATION_AGE_SECONDS}"
echo "mode: read_only_diagnostic"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_expansion_surface_map \
  --log-dir "${LOG_DIR}" \
  --max-observation-age-seconds "${MAX_OBSERVATION_AGE_SECONDS}" \
  --text
