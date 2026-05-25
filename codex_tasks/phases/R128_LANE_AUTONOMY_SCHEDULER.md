# R128 Lane Autonomy Scheduler

## Phase

`R128`

## Branch

`r128-lane-autonomy-scheduler`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

R127 creates the non-executing autonomous lane control loop. R128 should schedule that loop at a configurable cadence so Hammer Radar can keep watching fresh lane candidates without manual command polling.

## Assigned Agents

- builder: implement scheduler scaffold
- index: verify reuse of R127/R122/R123/R125 surfaces and update phase index
- qa: validate scheduler preview and audit behavior
- security: verify no live execution, no Binance order calls, no env mutation

## Main Objective

Schedule the R127 lane-autonomy control loop periodically in non-executing or paper-only mode, with compact operator status and append-only audit records.

## Capability Scan

Inspect:

- `src/app/hammer_radar/operator/lane_autonomy_control_loop.py`
- existing scheduler tasks under `src/app/hammer_radar/`
- `src/app/hammer_radar/operator/inspect.py`
- `logs/hammer_radar_forward/` ledger conventions
- `configs/hammer_radar/lane_controls.json`
- R122-R127 docs and tests

## Reuse / Extend / Create Decision

- Reuse R127 decision status builder.
- Reuse R122 lane controls and R123 fresh signal routing through R127.
- Reuse existing scheduler patterns if present.
- Create only the scheduler wrapper and audit surface needed for cadence/status.

## Safety Constraints

- No real orders.
- No Binance order endpoints.
- No signed requests.
- No env mutation.
- No live endpoint.
- No global live flag changes.
- Scheduler defaults to preview/non-executing mode.
- Paper-only integration, if added, must use existing R125 confirmation and safety semantics.

## Expected Behavior

The scheduler should support:

- configurable cadence
- preview/non-executing default
- optional paper-only mode if explicitly scoped
- append-only scheduler audit ledger
- compact operator status summary
- explicit safety fields proving no order, no payload, no network, and no secrets

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <changed_files>
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/<r128_tests>.py
```

## Final Report Format

Report branch, classification, capability scan, reuse decision, duplicate risk, files changed, tests run, scheduler safety result, and blockers.
