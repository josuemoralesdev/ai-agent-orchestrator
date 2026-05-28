# R144 Signal To Watcher Eligibility Trace

## Phase

`R144`

## Branch

`r144-signal-to-watcher-eligibility-trace`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

R142 can time out even when visible records exist in `signals.ndjson` because those visible signals are not necessarily watcher-eligible routed candidates. R144 should explain the full source chain from local signal to watcher consumption so the operator can see the exact blocker without weakening freshness, routing, paper proof, or live-readiness gates.

## Assigned Agents

- builder: implement a scoped diagnostic trace
- index: map existing signal/router/watcher surfaces before adding code
- qa: verify trace output and no mutation
- security: confirm no live execution, no Binance calls, no secrets

## Main Objective

Create a read-only trace that explains why each visible signal does or does not become watcher-eligible for the R142/R143 tiny-live lanes.

## Required Trace Stages

- signal exists
- timeframe and direction match target lane
- `entry_mode` derivation
- candidate creation
- router emission
- paper eligibility
- watcher consumption
- exact reason when a visible signal is not watcher-eligible

## Capability Scan

Inspect:

- `src/app/hammer_radar/operator/fresh_signal_router.py`
- `src/app/hammer_radar/operator/fresh_candidate_paper_proof_capture_loop.py`
- `src/app/hammer_radar/operator/lane_autonomy_control_loop.py`
- `src/app/hammer_radar/operator/lane_autonomy_scheduler.py`
- `src/app/hammer_radar/operator/autonomous_paper_lane_executor_integration.py`
- `src/app/hammer_radar/operator/autonomous_paper_lane_execution.py`
- `src/app/hammer_radar/operator/inspect.py`
- `configs/hammer_radar/lane_controls.json`
- `tests/hammer_radar/`
- `docs/hammer_radar/live_readiness/`

## Safety Constraints

- Do not place orders.
- Do not call Binance.
- Do not create executable order or protective payloads.
- Do not sign requests.
- Do not mutate env, configs, ledgers, or global live flags by default.
- Do not disable kill switches.
- Do not weaken freshness or watcher eligibility checks.

## Expected Output

Add a read-only inspect command that returns per-signal trace rows with:

- signal id / candidate id when available
- lane key candidates
- source timestamp and freshness
- timeframe, direction, and entry mode evidence
- router status and blockers
- paper eligibility status and blockers
- watcher eligibility status and blockers
- recommended next safe diagnostic command
- safety flags proving no execution or mutation

## Validation

Run focused py_compile and targeted tests first, then broader `tests/hammer_radar` if scope warrants.
