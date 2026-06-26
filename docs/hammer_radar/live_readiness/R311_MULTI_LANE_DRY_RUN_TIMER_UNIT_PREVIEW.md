# R311 Multi-Lane Dry-Run Timer Unit Preview

## Why R311 Exists

R310 added a multi-lane dry-run observation scheduler for the baseline first Tiny Live lane, primary observed lanes, and secondary watch-only lanes. R311 prepares a systemd service/timer design preview for recurring R310 observation ticks without installing or starting anything.

## What The Previewed Unit/Timer Would Do

Previewed service:

```text
hammer-multi-lane-dry-run-observation.service
```

Previewed timer:

```text
hammer-multi-lane-dry-run-observation.timer
```

Previewed command:

```bash
/home/josue/workspace/kernel/ai-agent-orchestrator-main/.venv/bin/python \
  -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler \
  --log-dir /home/josue/workspace/kernel/ai-agent-orchestrator-main/logs/hammer_radar_forward \
  --once
```

Previewed cadence:

```text
OnBootSec=2min
OnUnitActiveSec=60s
AccuracySec=10s
```

The command records an R310 observation tick only. It does not arm lanes, submit orders, create executable payloads, or call Binance order/test-order/leverage/margin mutation endpoints.

## Why It Is Not Installed

R311 is a preview packet only. It does not:

- write files under `/etc/systemd/system`
- add repo-local systemd templates
- run `systemctl`
- run `daemon-reload`
- install, enable, start, stop, or restart units
- mutate risk contracts, arming state, config, env, or live flags

Future installation requires a separate human-reviewed phase. The preview phrase is:

```text
INSTALL MULTI LANE DRY RUN OBSERVATION TIMER
```

In R311 this phrase is inactive and non-executable.

## How To Inspect Preview

Direct module:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_unit_preview --log-dir logs/hammer_radar_forward
```

No-write text preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_unit_preview --log-dir logs/hammer_radar_forward --no-write --text
```

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward multi-lane-dry-run-timer-unit-preview
```

Operator script:

```bash
bash scripts/hammer_print_r311_multi_lane_dry_run_timer_unit_preview.sh
```

Output ledger:

```text
logs/hammer_radar_forward/multi_lane_dry_run_timer_unit_preview.ndjson
```

## How To Verify Safety

Expected locked fields:

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
submit_allowed=false
final_command_available=false
real_order_forbidden=true
binance_order_endpoint_called=false
binance_test_order_endpoint_called=false
leverage_change_called=false
margin_change_called=false
secrets_shown=false
paper_live_separation_intact=true
autonomous_arming_state_changed=false
global_live_flags_changed=false
risk_contract_config_mutated=false
config_written=false
env_written=false
env_mutated=false
systemd_unit_mutated=false
systemd_unit_installed=false
systemd_timer_installed=false
systemd_unit_enabled=false
systemd_timer_enabled=false
systemd_unit_started=false
systemd_timer_started=false
daemon_reload_called=false
scheduler_started=false
```

Config mutation check:

```bash
git diff -- configs/hammer_radar/tiny_live_risk_contracts.json configs/hammer_radar/autonomous_arming_state.json
```

## What Not To Do

Do not manually install, enable, start, stop, restart, or reload systemd from R311 output. Do not treat the preview phrase as active authorization. Do not edit live flags, risk contracts, arming state, env files, or kill-switch behavior as part of this phase.

## Recommended R312 Paths

If R311 is clean:

```text
R312 Human-Reviewed Multi-Lane Timer Install Gate
```

That phase may install or enable the timer only after explicit operator confirmation.

If R311 shows blockers:

```text
R312 Timer Preview Repair
```
