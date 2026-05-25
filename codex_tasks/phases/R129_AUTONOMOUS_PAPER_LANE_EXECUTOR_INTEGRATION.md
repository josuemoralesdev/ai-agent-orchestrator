# R129 Autonomous Paper Lane Executor Integration

## Phase

`R129`

## Branch

`r129-autonomous-paper-lane-executor-integration`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: HIGH

## Reason

R128 schedules the R127 lane autonomy loop and can record scheduler ticks and decisions. R129 should connect confirmed scheduler mode to the existing R125 autonomous paper lane execution path so eligible fresh lane decisions can become paper-only execution records automatically.

## Main Objective

Integrate scheduler-confirmed autonomy decisions with the R125 paper-only lane executor while preserving all live-trading protections.

## Capability Scan

Inspect:

- `src/app/hammer_radar/operator/lane_autonomy_scheduler.py`
- `src/app/hammer_radar/operator/lane_autonomy_control_loop.py`
- `src/app/hammer_radar/operator/autonomous_paper_lane_execution.py`
- `src/app/hammer_radar/operator/fresh_signal_router.py`
- `src/app/hammer_radar/operator/lane_control.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/test_lane_autonomy_scheduler.py`
- `tests/hammer_radar/test_autonomous_paper_lane_execution.py`
- `docs/hammer_radar/live_readiness/R125_AUTONOMOUS_PAPER_LANE_EXECUTION.md`
- `docs/hammer_radar/live_readiness/R127_LANE_AUTONOMY_CONTROL_LOOP.md`
- `docs/hammer_radar/live_readiness/R128_LANE_AUTONOMY_SCHEDULER.md`

## Required Behavior

- Paper only.
- No real orders.
- No Binance order endpoints.
- No signed requests.
- No env mutation.
- Respect lane max daily trades.
- Respect lane cooldowns.
- Respect lane max daily loss policy.
- Record paper executions automatically only after confirmed paper scheduler mode.
- Reuse R125 paper execution records and ledger.
- Reuse R127 decision logic and R128 scheduler confirmation semantics.

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not create Binance order payloads.
- Do not call account or balance endpoints.
- Do not modify env flags.
- Do not expose secrets.
- Do not weaken paper/live separation.
- Preserve human approval gates and R106/global gates.

## Expected Outputs

- Updated scheduler or adapter that can call R125 paper execution safely.
- CLI support for confirmed paper scheduler mode.
- Tests proving paper records are created only after exact confirmation.
- Tests proving no real order, payload, Binance, network, or env mutation occurs.
- Updated R129 docs and phase index entry.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/lane_autonomy_scheduler.py src/app/hammer_radar/operator/autonomous_paper_lane_execution.py src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_lane_autonomy_scheduler.py tests/hammer_radar/test_autonomous_paper_lane_execution.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Do Not

- Do not implement tiny-live autonomous execution.
- Do not create a live order endpoint.
- Do not install or enable systemd services.
- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart services unless explicitly instructed.
