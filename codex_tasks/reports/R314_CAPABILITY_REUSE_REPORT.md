# R314 Capability Reuse Report

## Phase Classification

- Primary classification: `EXTENSION OF EXISTING CAPABILITY`
- Secondary classification: `DIAGNOSTIC / AUDIT`
- Duplicate risk level: `MEDIUM`
- Reason: R314 summarizes existing R310/R312/R313 observation, timer, final-console, and paper-refresh signals. It adds a compact health panel instead of a new scheduler, install gate, arming surface, or trading path.

## Capability Scan

### Reusable Ledgers

- `logs/hammer_radar_forward/multi_lane_dry_run_observation.ndjson`
  - R310 source of latest observation tick, baseline lane, primary lanes, secondary watch-only lanes, risk-contract status, candidate visibility, and locked safety fields.
- `logs/hammer_radar_forward/multi_lane_dry_run_timer_install_gate.ndjson`
  - R312/R313 evidence for human-reviewed install, files written, real systemctl calls, and install gate status.
- `logs/hammer_radar_forward/paper_refresh_runs.ndjson`
  - Paper refresh health, failed tasks, critical/non-critical classification, and latest degraded state.
- `logs/hammer_radar_forward/multi_lane_observation_health_panel.ndjson`
  - New R314 read-only panel ledger. This is the only R314 write.

### Reusable Final Console Surface

- `src/app/hammer_radar/operator/tiny_live_final_console.py`
  - Reuses `build_final_tiny_live_authorization_gate_panel`.
  - Supplies final gate status, blockers, real-order-forbidden state, submit availability, final command availability, armed lane key, and timer health fields.
  - R314 only reads this surface. It does not record a final-console review, arm controls, create final commands, or submit.

### Reusable Paper Refresh Status

- `src/app/hammer_radar/operator/paper_refresh_scheduler.py`
  - Reuses `load_refresh_runs`.
  - Reuses health values:
    - `PAPER_REFRESH_HEALTHY`
    - `PAPER_REFRESH_DEGRADED_NON_CRITICAL`
    - `PAPER_REFRESH_CRITICAL_FAILURE`
  - Treats `eth_paper_outcome`-only degradation as accepted non-critical context, not a fatal R314 blocker.

### Timer Health Sources

- `src/app/hammer_radar/operator/multi_lane_dry_run_timer_unit_preview.py`
  - Reuses `SERVICE_NAME` and `TIMER_NAME`.
- `src/app/hammer_radar/operator/multi_lane_dry_run_timer_install_gate.py`
  - Reuses install ledger semantics.
- Read-only systemd commands, injectable for tests:
  - `systemctl is-enabled hammer-multi-lane-dry-run-observation.timer`
  - `systemctl is-active hammer-multi-lane-dry-run-observation.timer`
  - `systemctl show hammer-multi-lane-dry-run-observation.service -p Result -p ExecMainStatus`
  - `systemctl is-active hammer-paper-refresh.service`

R314 never calls `daemon-reload`, `enable`, `start`, `stop`, `restart`, or install commands.

## Existing Docs Checked

- `docs/hammer_radar/live_readiness/R310_MULTI_LANE_DRY_RUN_OBSERVATION_SCHEDULER.md`
- `docs/hammer_radar/live_readiness/R312_HUMAN_REVIEWED_MULTI_LANE_TIMER_INSTALL_GATE.md`
- `docs/hammer_radar/`

## Existing Modules Checked

- `src/app/hammer_radar/operator/multi_lane_dry_run_observation_scheduler.py`
- `src/app/hammer_radar/operator/multi_lane_dry_run_timer_install_gate.py`
- `src/app/hammer_radar/operator/multi_lane_dry_run_timer_unit_preview.py`
- `src/app/hammer_radar/operator/tiny_live_final_console.py`
- `src/app/hammer_radar/operator/paper_refresh_scheduler.py`
- `src/app/hammer_radar/operator/inspect.py`

## Existing Tests Checked

- `tests/hammer_radar/test_multi_lane_dry_run_observation_scheduler.py`
- `tests/hammer_radar/test_multi_lane_dry_run_timer_install_gate.py`
- `tests/hammer_radar/test_paper_refresh_scheduler.py`
- Nearby systemd/timer safety tests under `tests/hammer_radar/`

## Existing Endpoints Checked

- Local final console endpoint documented in R312:
  - `GET http://127.0.0.1:8015/tiny-live/final-console`
- R314 does not add or expose a public API endpoint.

## Existing CLI Commands Checked

- `inspect multi-lane-dry-run-observation`
- `inspect multi-lane-dry-run-timer-unit-preview`
- `inspect multi-lane-dry-run-timer-install-gate`
- `inspect paper-refresh-status`
- `inspect paper-refresh-runs`

R314 adds:

- `inspect multi-lane-observation-health-panel`

## Existing Scheduler Tasks Checked

- R310 one-shot observation command used by the timer.
- R312 systemd install gate.
- Paper refresh scheduler status and run ledger.

R314 does not add a scheduler task.

## Existing Logs / Ledgers / Configs Checked

- `logs/hammer_radar_forward/multi_lane_dry_run_observation.ndjson`
- `logs/hammer_radar_forward/multi_lane_dry_run_timer_install_gate.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`

R314 does not write configs or arming state.

## Duplicate Risks

- Similar existing module: R310 observation scheduler already prints a detailed text view.
- Similar existing module: R312 timer install gate already records install status.
- Similar existing final-console surface: final authorization gate panel already summarizes final safety.
- Similar existing paper-refresh surface: paper refresh status already summarizes refresh health.

Risk: creating another raw JSON-heavy verification command would duplicate existing outputs and continue terminal flooding.

Mitigation: R314 consumes the existing ledgers/surfaces and emits a compact operator panel with only top-level summaries, counts, blocker lists, and locked safety flags.

## Chosen Health-Panel Implementation Path

Create `src/app/hammer_radar/operator/multi_lane_observation_health_panel.py` as a small adapter layer that:

- reads the latest R310 observation row
- reads R312/R313 timer install evidence
- checks systemd state with read-only commands only
- reads final live safety from the final console panel
- reads latest paper refresh health
- appends only `multi_lane_observation_health_panel.ndjson`
- exposes compact text, JSON, and inspect-route output

## Why R314 Does Not Install / Mutate / Trade

R314 has no apply mode, no confirmation phrase, no write-gate behavior, no arming call, no live flag mutation, no risk-contract writer, no config writer, no env writer, no final submit command, and no Binance order/test-order/leverage/margin call.

Its safety fields remain locked:

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
scheduler_started=false
```
