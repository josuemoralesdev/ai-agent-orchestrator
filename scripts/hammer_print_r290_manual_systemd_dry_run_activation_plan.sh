#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_template="${repo_root}/ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template"
timer_template="${repo_root}/ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template"
r289_checklist="${repo_root}/docs/hammer_radar/live_readiness/R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md"
r290_checklist="${repo_root}/docs/hammer_radar/live_readiness/R290_MANUAL_SYSTEMD_DRY_RUN_TIMER_ACTIVATION_CHECKLIST.md"

echo "=== R290 DRY RUN PRINT ONLY ==="
echo "This helper prints manual activation commands for operator review."
echo "It does not run sudo, systemctl, cp, install, rm, copy files, mutate configs, or install units."
echo "It exits after printing text."
echo
echo "Templates:"
echo "  ${service_template}"
echo "  ${timer_template}"
echo "Checklists:"
echo "  ${r289_checklist}"
echo "  ${r290_checklist}"
echo
echo "Preflight commands:"
echo "  git status --short --branch"
echo "  sed -n '1,220p' '${service_template}'"
echo "  sed -n '1,220p' '${timer_template}'"
echo "  PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-autonomous-trigger-scheduler-activation-readiness | jq ."
echo "  curl -sS http://127.0.0.1:8015/readiness | jq ."
echo "  curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq ."
echo "  curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '.autonomous_trigger_scheduler_activation_panel'"
echo
echo "Manual install commands for the operator to run only after readiness is READY:"
echo "  sudo install -m 0644 '${service_template}' /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service"
echo "  sudo install -m 0644 '${timer_template}' /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer"
echo "  sudo systemctl daemon-reload"
echo
echo "Manual start command:"
echo "  sudo /usr/bin/systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer"
echo
echo "Status, journal, and timer commands:"
echo "  systemctl status hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager"
echo "  systemctl status hammer-autonomous-trigger-scheduler-dry-run.service --no-pager"
echo "  systemctl list-timers hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager"
echo "  journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager"
echo
echo "First and second tick smoke commands:"
echo "  sleep 150"
echo "  systemctl list-timers hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager"
echo "  journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager"
echo "  curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq ."
echo "  curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '{status, autonomous_trigger_scheduler_activation_panel, autonomous_trigger_scheduler_systemd_panel, autonomous_trigger_scheduler_panel, safety}'"
echo "  sleep 150"
echo "  systemctl list-timers hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager"
echo "  journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager"
echo
echo "Safety grep command:"
echo "  grep -R '\"'\"'order_placed\"'\"': true\\|\"'\"'real_order_placed\"'\"': true\\|\"'\"'execution_attempted\"'\"': true\\|\"'\"'final_command_available\"'\"': true\\|\"'\"'submit_allowed\"'\"': true\\|\"'\"'executable_payload_created\"'\"': true\\|\"'\"'secrets_shown\"'\"': true' -n logs/hammer_radar_forward/tiny_live*.ndjson logs/hammer_radar_forward/*autonomous*.ndjson 2>/dev/null || true"
echo
echo "Rollback commands:"
echo "  sudo systemctl disable --now hammer-autonomous-trigger-scheduler-dry-run.timer"
echo "  sudo systemctl stop hammer-autonomous-trigger-scheduler-dry-run.service"
echo "  sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service"
echo "  sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer"
echo "  sudo systemctl daemon-reload"
echo
echo "R290 remains dry-run timer activation only: no submit, no order, no executable payload, no Binance order endpoint."
exit 0
