# R289 Autonomous Trigger Scheduler Systemd Install Checklist

R289 prepares repo-local systemd service and timer templates for the autonomous
trigger scheduler dry-run tick. It does not install, enable, start, stop, or
restart any systemd unit.

## What This Installs

If manually installed later by the operator, the timer runs:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-once \
  --record-autonomous-trigger-scheduler \
  --operator-id systemd_scheduler \
  --reason "systemd dry-run autonomous trigger scheduler tick; no submit."
```

The command records autonomous trigger scheduler ticks to the local Hammer Radar
logs. It remains dry-run only.

## What It Does Not Do

- Does not place orders.
- Does not call Binance order, order-validation, leverage, or margin mutation endpoints.
- Does not create executable order payloads.
- Does not make a final live submit command available.
- Does not enable live execution.
- Does not disable the global kill switch.
- Does not mutate env files, risk contracts, live config, or lane controls.
- Does not require per-signal operator approval gates.
- Does not expose secrets, signatures, signed URLs, API keys, or auth headers.

## Safety Assumptions

- The operator arms/disarms lanes, tunes risk, monitors alerts/logs, and can kill
  the system.
- The machine auto-triggers only when armed and all gates are open.
- R289 remains dry-run scheduler only, no live orders.
- Do not install if `final_command_available=true` or `submit_allowed=true`
  appears anywhere unexpectedly.

## Preflight Commands

```bash
git status --short --branch
sed -n '1,220p' ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template
sed -n '1,220p' ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template
bash scripts/hammer_print_autonomous_trigger_scheduler_systemd_install_plan.sh
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-systemd-template-status
```

## Safety Grep

```bash
pattern_order="fapi/v1/"'order'
pattern_validation_prefix="test"'.*'
pattern_order_word="order"
pattern_secret_key="BINANCE_API_"'KEY='
pattern_secret_value="BINANCE_API_"'SECRET='
pattern_leverage="leverage_"'change'
pattern_margin="margin_"'change'
pattern_final_command="final-live-"'submit'
pattern_submit_live="submit-"'live'
pattern_sudo_start="sudo systemctl "'start'
pattern_sudo_enable="sudo systemctl "'enable'
grep -R "${pattern_order}\|${pattern_validation_prefix}${pattern_order_word}\|${pattern_leverage}\|${pattern_margin}\|${pattern_secret_value}\|${pattern_secret_key}\|${pattern_final_command}\|${pattern_submit_live}\|${pattern_sudo_start}\|${pattern_sudo_enable}" -n \
  ops/systemd/hammer-radar \
  docs/hammer_radar/live_readiness/R289_AUTONOMOUS_TRIGGER_SCHEDULER_SYSTEMD_INSTALL_CHECKLIST.md \
  scripts/hammer_print_autonomous_trigger_scheduler_systemd_install_plan.sh \
  2>/dev/null || true
```

The grep should not find unsafe executable content. Manual install text may
include explicit operator commands; review every match before installing.

## Manual Install

Copy templates into systemd unit names:

```bash
sudo install -m 0644 ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service
sudo install -m 0644 ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer
```

Reload systemd:

```bash
sudo systemctl daemon-reload
```

Start the timer only after preflight and safety grep are clean:

```bash
sudo /usr/bin/systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer
```

Do not enable the timer until the operator has reviewed several dry-run ticks.

## Status And Journals

```bash
systemctl status hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager
systemctl status hammer-autonomous-trigger-scheduler-dry-run.service --no-pager
journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager
```

## API Verification

```bash
curl -s http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/systemd-template-status | jq .
curl -s http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq .
curl -s http://127.0.0.1:8015/tiny-live/final-console | jq '.autonomous_trigger_scheduler_systemd_panel'
```

## Rollback

```bash
sudo systemctl disable --now hammer-autonomous-trigger-scheduler-dry-run.timer
sudo systemctl stop hammer-autonomous-trigger-scheduler-dry-run.service
sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service
sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer
sudo systemctl daemon-reload
```

After rollback, verify:

```bash
systemctl status hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager
systemctl status hammer-autonomous-trigger-scheduler-dry-run.service --no-pager
```

## Operator Stop Conditions

Stop or do not install if any status, API response, ledger, or console output
shows:

```text
final_command_available=true
submit_allowed=true
order_placed=true
real_order_placed=true
execution_attempted=true
binance_order_endpoint_called=true
binance_order_validation_endpoint_called=true
executable_payload_created=true
secrets_shown=true
```

R289 does not authorize live submit. It only prepares reviewable dry-run
operational wiring for a later manual operator install.
