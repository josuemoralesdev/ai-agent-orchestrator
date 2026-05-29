# R151 After Fresh Proof Tiny-Live Ready Recheck

## Phase

`R151`

## Branch

`r151-after-fresh-proof-tiny-live-ready-recheck`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

R151 should run only after R150/R142 captures fresh paper proof for the target `tiny_live` lanes. Its job is to recheck the tiny-live readiness chain and prepare a final review packet without executing live trades.

## Assigned Agents

- builder: implement scoped recheck wiring only if existing surfaces need a wrapper
- index: verify source-of-truth reuse and update phase index
- qa: run focused recheck and safety validation
- security: enforce live-trading and Binance boundaries

## Main Objective

Recheck tiny-live gates, live safety, Binance read-only/funding evidence, and paper-proof evidence after fresh proof is captured, then prepare a final tiny-live readiness packet for human review.

## Capability Scan

Inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/`
- `src/app/hammer_radar/operator/fresh_candidate_paper_proof_capture_loop.py`
- `src/app/hammer_radar/operator/watch_heartbeat.py`
- `src/app/hammer_radar/operator/post_bridge_watcher_proof_capture_recheck.py`
- `src/app/hammer_radar/operator/first_tiny_live_lane_execution_gate.py`
- `src/app/hammer_radar/operator/live_safety.py`
- `src/app/hammer_radar/operator/binance_readonly.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`
- existing ledgers under `logs/hammer_radar_forward/`

## Reuse / Extend / Create Decision

- Existing capability reused: R150/R142 watcher ledgers, R146 post-bridge recheck, R126 first tiny-live lane gate, live-safety, Binance read-only status.
- Existing capability extended: only add a small wrapper/report if needed.
- New capability created: final R151 readiness packet only if no existing command composes these checks.
- Why new code is necessary: to produce one post-proof review packet and avoid manual mismatch after capture.
- Why this does not duplicate prior work: it composes existing non-executing checks and does not replace R106/R126/R150.

## Duplicate Risk Report

- Similar existing modules: R126, R146, R149, R150.
- Similar existing endpoints: operator inspect commands for tiny-live gates and safety.
- Similar existing CLI commands: `post-bridge-watcher-proof-capture-recheck`, `first-tiny-live-lane-execution-gate`, `live-safety`, `binance-readonly-status`.
- Similar existing scheduler tasks: none required.
- Similar existing docs: R146, R149, R150.
- Risk: HIGH.
- Mitigation: compose existing outputs; do not implement a new live-readiness authority.

## Files Expected

- Optional runtime wrapper under `src/app/hammer_radar/operator/`
- Optional tests under `tests/hammer_radar/`
- `docs/hammer_radar/live_readiness/R151_AFTER_FRESH_PROOF_TINY_LIVE_READY_RECHECK.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`

## Tests Required

- Fresh proof captured state is detected from append-only ledgers.
- Missing proof keeps R151 blocked.
- Tiny-live gate checks are re-run for target lanes.
- Live safety and Binance read-only summaries are included.
- No live execution, no order payloads, no signed requests, no env/config/global mutation.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <changed_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <targeted_tests>
```

## Safety Constraints

- No live execution unless explicitly authorized in a later phase.
- Do not place orders.
- Do not create executable Binance order payloads.
- Do not create protective payloads.
- Do not call Binance order, test-order, protective, account, order, private, or signed endpoints.
- Do not mutate env files.
- Do not mutate global live flags.
- Do not disable the kill switch.
- Do not bypass R106/global gates.
- Do not bypass protective policy.
- Do not bypass freshness.

## Do Not

- Do not run `sudo`.
- Do not start, stop, restart, enable, or disable services.
- Do not commit, merge, tag, push, or deploy.
- Do not perform live trading actions.

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
