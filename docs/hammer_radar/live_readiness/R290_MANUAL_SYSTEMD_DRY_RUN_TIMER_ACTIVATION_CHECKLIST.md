# R290 Manual Systemd Dry-Run Timer Activation Checklist

## Purpose

R290 gives the operator a repeatable activation packet for manually installing
and starting the R289 autonomous trigger scheduler dry-run timer. Codex does not
install, start, enable, reload, remove, or mutate systemd units in this phase.

## What This Activates

If the operator manually installs and starts the timer, systemd runs the
repo-local dry-run scheduler tick every two minutes:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-once \
  --record-autonomous-trigger-scheduler \
  --operator-id systemd_scheduler \
  --reason "systemd dry-run autonomous trigger scheduler tick; no submit."
```

The tick is record-only and dry-run only.

## What This Does NOT Activate

- No live orders.
- No Binance order endpoint.
- No Binance leverage or margin mutation endpoint.
- No executable payload.
- No final live submit command.
- No live execution flag.
- No global kill-switch disable.
- No env, risk-contract, live-config, or lane-control writes.
- No per-signal approval gate.

## Operator Doctrine

The operator does not approve each signal. The operator arms or disarms lanes,
tunes risk, monitors alerts and logs, and can kill the system. The machine
auto-triggers only when dry-run armed and all gates are open.

## Preflight Checks Before Install

```bash
git status --short --branch
sed -n '1,220p' ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template
sed -n '1,220p' ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template
bash scripts/hammer_print_r290_manual_systemd_dry_run_activation_plan.sh
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-activation-readiness | jq .
```

Do not install if `final_command_available` or `submit_allowed` ever returns
`true`.

## Manual Install Commands

Run these manually only after the activation readiness packet is
`ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL`:

```bash
sudo install -m 0644 ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service
sudo install -m 0644 ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer
sudo systemctl daemon-reload
```

## Manual Start Command

```bash
sudo /usr/bin/systemctl start hammer-autonomous-trigger-scheduler-dry-run.timer
```

Do not enable the timer until several dry-run ticks have been reviewed.

## Wait For Timer Tick

```bash
sleep 150
systemctl list-timers hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager
```

## Smoke Checks After First/Second Tick

```bash
journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager
curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq .
curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '{
  status,
  autonomous_trigger_scheduler_activation_panel,
  autonomous_trigger_scheduler_systemd_panel,
  autonomous_trigger_scheduler_panel,
  safety
}'
sleep 150
systemctl list-timers hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager
journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager
```

## API Verification

```bash
curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/activation-readiness | jq .
curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/systemd-template-status | jq .
curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq .
curl -sS http://127.0.0.1:8015/readiness | jq .
```

Expected safety fields:

```text
codex_install_performed=false
codex_systemctl_start_performed=false
codex_systemctl_enable_performed=false
codex_sudo_performed=false
dry_run_only=true
live_execution_enabled=false
per_signal_operator_approval_required=false
final_command_available=false
submit_allowed=false
real_order_forbidden=true
```

## Journal Verification

```bash
systemctl status hammer-autonomous-trigger-scheduler-dry-run.timer --no-pager
systemctl status hammer-autonomous-trigger-scheduler-dry-run.service --no-pager
journalctl -u hammer-autonomous-trigger-scheduler-dry-run.service -n 120 --no-pager
```

Expected journal evidence includes the scheduler inspect command and the phrase
`no submit`.

## Safety Grep Verification

```bash
grep -R '"order_placed": true\|"real_order_placed": true\|"execution_attempted": true\|"final_command_available": true\|"submit_allowed": true\|"executable_payload_created": true\|"secrets_shown": true' -n \
  logs/hammer_radar_forward/tiny_live*.ndjson \
  logs/hammer_radar_forward/*autonomous*.ndjson \
  2>/dev/null || true
```

Expected good output is no unsafe matches.

## Rollback Commands

```bash
sudo systemctl disable --now hammer-autonomous-trigger-scheduler-dry-run.timer
sudo systemctl stop hammer-autonomous-trigger-scheduler-dry-run.service
sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.service
sudo rm -f /etc/systemd/system/hammer-autonomous-trigger-scheduler-dry-run.timer
sudo systemctl daemon-reload
```

## Expected Good Output

- Activation readiness status is `ACTIVATION_READINESS_READY_FOR_MANUAL_INSTALL`.
- Template status is `SYSTEMD_TEMPLATE_READY`.
- Timer status shows the dry-run timer loaded and scheduled.
- Journal shows scheduler ticks with `no submit`.
- Scheduler status remains dry-run and no-submit.
- Final console activation panel shows Codex install/start/enable/sudo all false.
- Safety grep returns no unsafe true flags.

## Stop Criteria

Stop the timer or do not install if any output shows:

```text
final_command_available=true
submit_allowed=true
order_placed=true
real_order_placed=true
execution_attempted=true
binance_order_endpoint_called=true
executable_payload_created=true
secrets_shown=true
codex_install_performed=true
codex_systemctl_start_performed=true
codex_systemctl_enable_performed=true
codex_sudo_performed=true
```

## Red Flags

- The activation readiness packet is blocked.
- The approval API is not reachable on `http://127.0.0.1:8015`.
- The scheduler status or final console reports submit availability.
- The journal contains unexpected command text.
- Any live flag is true.
- Any secret, signature, signed URL, or credential value appears in output.
- Any systemd command was run by Codex instead of the human operator.

## Next Phase After Activation

After the operator manually installs and starts the dry-run timer, the next phase
should inspect first and second tick evidence, journal output, scheduler ledgers,
final console panels, and safety grep results. The next phase remains no-submit
unless a future explicit phase says otherwise.
