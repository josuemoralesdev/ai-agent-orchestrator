# R131 Live Lane Kill-Switch Rehearsal

## Phase

`R131`

## Branch

`r131-live-lane-kill-switch-rehearsal`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R130 can record operator authorization intent for a future tiny-live autonomous lane. Before any later live adapter or dry order-payload authorization phase, the system must rehearse kill-switch and rollback behavior for authorized lanes without placing orders.

## Main Objective

Create a non-executing rehearsal that verifies an R130-authorized lane can be disabled, global kill-switch semantics remain authoritative, rollback instructions are explicit, and the scheduler would stop respecting the lane after disablement.

## Capability Scan

Inspect:

- `src/app/hammer_radar/operator/first_tiny_live_autonomous_lane_authorization.py`
- `src/app/hammer_radar/operator/lane_control.py`
- `src/app/hammer_radar/operator/lane_command_interface.py`
- `src/app/hammer_radar/operator/lane_autonomy_control_loop.py`
- `src/app/hammer_radar/operator/lane_autonomy_scheduler.py`
- `src/app/hammer_radar/operator/first_tiny_live_lane_execution_gate.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/inspect.py`
- `configs/hammer_radar/lane_controls.json`
- R130 authorization ledger
- R124/R126/R127/R128/R130 tests and docs

## Required Behavior

- Load recent R130 authorized tiny-live lane records.
- Preview disabling the lane through R124 lane-command semantics.
- Verify the selected lane would no longer produce tiny-live gate-review/autonomy intent after disablement.
- Verify global kill switch semantics still block live execution.
- Verify rollback path is acknowledged and documented.
- Emit compact CLI JSON and optional append-only rehearsal ledger.

## Safety Constraints

- Do not place real orders.
- Do not create Binance order payloads.
- Do not call Binance order endpoints.
- Do not send signed requests.
- Do not mutate env files.
- Do not enable global live execution.
- Do not alter global live gates.
- Do not install/start systemd services.
- Do not run `sudo`.

## Expected Outputs

- R131 operator module.
- R131 CLI mode in `inspect.py`.
- R131 doc and phase index update.
- Tests proving no orders, no Binance calls, no env mutation, no config mutation by default, and correct kill-switch/rollback rehearsal status.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_live_lane_kill_switch_rehearsal.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Do Not

- Do not implement real execution.
- Do not place orders.
- Do not call Binance.
- Do not mutate env.
- Do not weaken kill switches.
- Do not commit, merge, tag, push, deploy, or restart services unless explicitly instructed.
