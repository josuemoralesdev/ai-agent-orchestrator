#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
CONFIRMATION_PHRASE="INSTALL MULTI LANE DRY RUN OBSERVATION TIMER"

echo "R312 HUMAN-REVIEWED MULTI-LANE TIMER INSTALL GATE"
echo "log_dir: ${LOG_DIR}"
echo
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate \
  --log-dir "${LOG_DIR}" \
  --no-ledger \
  --text
echo
echo "SERVICE/TIMER NAMES"
echo "service_name: hammer-multi-lane-dry-run-observation.service"
echo "timer_name: hammer-multi-lane-dry-run-observation.timer"
echo
echo "INSTALL PATH PREVIEW"
echo "service_install_path: /etc/systemd/system/hammer-multi-lane-dry-run-observation.service"
echo "timer_install_path: /etc/systemd/system/hammer-multi-lane-dry-run-observation.timer"
echo
echo "COMMAND PREVIEW"
echo "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate --log-dir ${LOG_DIR}"
echo
echo "CONFIRMATION PHRASE"
echo "${CONFIRMATION_PHRASE}"
echo
echo "APPLY COMMAND PREVIEW"
echo "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate --log-dir ${LOG_DIR} --apply --confirmation \"${CONFIRMATION_PHRASE}\""
echo
echo "R312 script is preview only."
echo "No apply flag is used by this script."
echo "No systemd files are installed, enabled, started, stopped, or reloaded by this script."
echo "Recommended R313 path: R313 Operator Apply Multi-Lane Timer Install + Health Verification if the operator chooses to install."
