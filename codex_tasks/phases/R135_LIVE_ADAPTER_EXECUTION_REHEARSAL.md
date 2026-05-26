# R135 Live Adapter Execution Rehearsal

## Phase

`R135`

## Branch

`r135-live-adapter-execution-rehearsal`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R134 creates a non-executing first tiny-live order payload dry authorization packet. R135 should rehearse the live adapter execution path boundaries against that packet without creating executable exchange material or contacting Binance.

## Assigned Agents

- builder: implement rehearsal-only adapter boundary checks
- index: verify reuse of R132/R134/R126/R130/R131/R106 surfaces
- qa: prove no orders, no Binance order endpoint calls, no signed request, and no network use
- security: enforce live-trading boundary and secret-handling constraints

## Main Objective

Rehearse the future live adapter execution path using the R134 dry authorization packet only, while preserving non-executing behavior.

## Capability Scan

Inspect:

- `src/app/hammer_radar/operator/first_tiny_live_order_payload_dry_authorization.py`
- `src/app/hammer_radar/operator/live_adapter_boundary_final_review.py`
- `src/app/hammer_radar/operator/first_tiny_live_lane_execution_gate.py`
- `src/app/hammer_radar/operator/first_tiny_live_autonomous_lane_authorization.py`
- `src/app/hammer_radar/operator/live_lane_kill_switch_rehearsal.py`
- `src/app/hammer_radar/execution/binance_futures_connector.py`
- `src/app/hammer_radar/execution/safety.py`
- `src/app/hammer_radar/operator/inspect.py`
- R132/R134 docs and tests
- existing connector preview/signing/submit/execute functions
- existing ledgers under `logs/hammer_radar_forward/`

## Reuse / Extend / Create Decision

- Reuse R134 dry authorization packet as the only input.
- Reuse R132 adapter boundary review.
- Reuse R126/R130/R131/R106 prerequisites.
- Do not duplicate live readiness logic.
- Create only a rehearsal wrapper if existing surfaces do not already expose the needed compact status.

## Required Safety Limits

- No real orders.
- No Binance order endpoint calls.
- No Binance test-order endpoint calls.
- No signed request creation.
- No executable payload creation.
- No account, balance, funding, or position network calls.
- No env mutation.
- No lane config mutation.
- No global live flag changes.
- No live endpoint.
- No service start/restart.

## Required Checks

R135 must verify:

- adapter function boundaries are visible but not invoked for execution
- R134 packet is non-executable
- protective payload preview remains non-executable or is blocked
- stop conditions prevent execution when R134 is blocked
- stop conditions prevent execution when R106/global gate is blocked
- stop conditions prevent execution when protective readiness is missing
- stop conditions prevent execution when credentials are missing
- stop conditions prevent execution when any safety field flips true

## Files Expected

Expected new or modified files:

- `src/app/hammer_radar/operator/live_adapter_execution_rehearsal.py`
- `src/app/hammer_radar/operator/inspect.py`
- `docs/hammer_radar/live_readiness/R135_LIVE_ADAPTER_EXECUTION_REHEARSAL.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `tests/hammer_radar/test_live_adapter_execution_rehearsal.py`

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/live_adapter_execution_rehearsal.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_live_adapter_execution_rehearsal.py
```

Broaden to `tests/hammer_radar` if shared live-readiness or connector surfaces are changed.

## Do Not

- Do not place orders.
- Do not call Binance.
- Do not call connector `submit_*` or `execute_live_order`.
- Do not call signed request builders.
- Do not mutate env/config.
- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart services.

## Final Report Format

Report:

- Branch:
- Phase Classification:
- Capability scan summary:
- Reuse / Extend / Create decision:
- Duplicate risk report:
- Files created:
- Files modified:
- Tests or checks run:
- Smoke checks run, if any:
- Safety result:
- Blockers, if any:
- Exact manual commands needed, if any:
