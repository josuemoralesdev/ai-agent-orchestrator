# R312 Human-Reviewed Multi-Lane Timer Install Gate

## Why R312 Exists

R311 produced a clean preview for recurring R310 multi-lane dry-run observation through:

```text
hammer-multi-lane-dry-run-observation.service
hammer-multi-lane-dry-run-observation.timer
```

R312 adds the human-reviewed gate that can write those unit files only after an exact phrase. Default behavior remains preview-only.

## Exact Phrase

```text
INSTALL MULTI LANE DRY RUN OBSERVATION TIMER
```

## Default Preview Behavior

Preview command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate --log-dir logs/hammer_radar_forward
```

Preview mode:

- renders the R311 service/timer content
- shows `/etc/systemd/system` install paths
- shows files that would be written
- shows that `daemon-reload`, timer enable, and timer start would be called in apply mode
- does not write systemd files
- does not call `systemctl`
- does not run `daemon-reload`
- does not mutate config, env, risk contracts, arming state, live flags, or kill switch behavior

Output ledger:

```text
logs/hammer_radar_forward/multi_lane_dry_run_timer_install_gate.ndjson
```

## Apply Behavior

Apply command shape:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_dry_run_timer_install_gate \
  --log-dir logs/hammer_radar_forward \
  --apply \
  --confirmation "INSTALL MULTI LANE DRY RUN OBSERVATION TIMER"
```

Apply mode:

- requires `--apply`
- requires the exact confirmation phrase
- writes only `hammer-multi-lane-dry-run-observation.service` and `hammer-multi-lane-dry-run-observation.timer`
- creates backups if target files already exist
- records files written and backups created
- calls systemctl only when `--systemctl-mode real` is explicitly selected

Codex validation for R312 must not run real apply against `/etc/systemd/system`.

## Mock Vs Real Systemctl

Default systemctl mode is mock:

```bash
--systemctl-mode mock
```

Mock mode records intended calls:

```text
systemctl daemon-reload
systemctl enable hammer-multi-lane-dry-run-observation.timer
systemctl start hammer-multi-lane-dry-run-observation.timer
```

Real mode:

```bash
--systemctl-mode real
```

Real mode is reserved for a future human-operated install phase. It still requires `--apply` and the exact phrase.

## Manual Verification After Install

After a human operator chooses to install in a future phase, verify:

```bash
systemctl list-unit-files | grep -E 'hammer-multi-lane-dry-run-observation' || true
systemctl status hammer-multi-lane-dry-run-observation.service hammer-multi-lane-dry-run-observation.timer --no-pager || true
journalctl -u hammer-multi-lane-dry-run-observation.service -n 80 --no-pager || true
```

Verify live safety:

```bash
curl -s http://127.0.0.1:8015/tiny-live/final-console | jq '.final_tiny_live_authorization_gate_panel | {status, blockers, real_order_forbidden, submit_allowed, final_command_available, current_real_candidate_lane_key, armed: .exact_lane_armed_state, timer: {timer_active: .readiness_matrix.timer_active, timer_health_status: .readiness_matrix.timer_health_status}}'
```

Verify no config or arming mutation:

```bash
git diff -- configs/hammer_radar/tiny_live_risk_contracts.json configs/hammer_radar/autonomous_arming_state.json
```

## Why It Still Does Not Trade

The timer runs the R310 observation scheduler with `--once`:

```bash
/home/josue/workspace/kernel/ai-agent-orchestrator-main/.venv/bin/python \
  -m src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler \
  --log-dir /home/josue/workspace/kernel/ai-agent-orchestrator-main/logs/hammer_radar_forward \
  --once
```

R310 observes dry-run lanes only. It does not arm lanes, submit orders, create final commands, write risk contracts, mutate env, or call Binance order/test-order/leverage/margin endpoints.

## Safety Fields

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
```

## What Not To Do

Do not run real apply from Codex validation. Do not run `systemctl daemon-reload`, `systemctl enable`, or `systemctl start` from R312 validation. Do not install into `/etc/systemd/system` unless a future phase explicitly authorizes a human operator apply. Do not change live flags, disable the kill switch, write env files, mutate risk contracts, mutate arming state, or submit final commands.

## Recommended R313 Paths

If R312 is clean and the operator chooses to install:

```text
R313 Operator Apply Multi-Lane Timer Install + Health Verification
```

If R312 shows blockers:

```text
R313 Timer Install Gate Repair
```
