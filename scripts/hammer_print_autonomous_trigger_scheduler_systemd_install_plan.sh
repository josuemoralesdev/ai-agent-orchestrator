#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_template="${repo_root}/ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template"
timer_template="${repo_root}/ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template"
checklist="${repo_root}/docs/hammer_radar/live_readiness/R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md"

echo "=== DRY RUN PRINT ONLY ==="
echo "This helper prints manual install commands for operator review."
echo "It does not run sudo, systemctl, copy files, mutate configs, or install units."
echo
echo "Templates:"
echo "  ${service_template}"
echo "  ${timer_template}"
echo "Checklist:"
echo "  ${checklist}"
echo
echo "Review templates:"
echo "  sed -n '1,220p' '${service_template}'"
echo "  sed -n '1,220p' '${timer_template}'"
echo
echo "Manual install commands for the operator to run only after checklist review:"
echo "  sudo install -m 0644 '${service_template}' /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service"
echo "  sudo install -m 0644 '${timer_template}' /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer"
echo "  sudo systemctl daemon-reload"
echo "  sudo /usr/bin/systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer"
echo
echo "Status and logs:"
echo "  systemctl status hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager"
echo "  systemctl status hammer-autonomous-trigger-scheduler-dry-run.service --no-pager"
echo "  journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager"
echo
echo "Rollback commands:"
echo "  sudo systemctl disable --now hammer-autonomous-trigger-scheduler-dry-run.timer"
echo "  sudo systemctl stop hammer-autonomous-trigger-scheduler-dry-run.service"
echo "  sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service"
echo "  sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer"
echo "  sudo systemctl daemon-reload"
echo
echo "R289 remains dry-run scheduler only: no submit, no order, no executable payload."
