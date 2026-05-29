# R150 After Fresh Proof Tiny-Live Ready Recheck

## Phase

`R150`

## Branch

`r150-after-fresh-proof-tiny-live-ready-recheck`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

Run only after the safe R149 watcher captures fresh paper proof. R150 should recheck the tiny-live readiness chain and prepare a final review packet without creating live execution authority.

## Assigned Agents

- builder: yes
- index: yes
- qa: yes
- security: yes

## Main Objective

Recheck current fresh proof, tiny-live lane gates, live safety, and Binance read-only/funding evidence, then prepare a final tiny-live readiness packet for operator review.

## Capability Scan

Inspect relevant existing surfaces before implementation:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R149_FAST_TINY_LIVE_LANE_STATUS_AND_PROOF_WATCH_PREP.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `src/app/hammer_radar/operator/post_tiny_live_mode_fresh_proof_watch.py`
- `src/app/hammer_radar/operator/fresh_candidate_paper_proof_capture_loop.py`
- `src/app/hammer_radar/operator/post_bridge_watcher_proof_capture_recheck.py`
- `src/app/hammer_radar/operator/first_tiny_live_lane_execution_gate.py`
- `src/app/hammer_radar/operator/live_safety.py`
- `src/app/hammer_radar/operator/binance_readonly.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`
- `configs/hammer_radar/lane_controls.json`
- `logs/hammer_radar_forward/fresh_candidate_paper_proof_capture_loop.ndjson`
- `logs/hammer_radar_forward/post_tiny_live_mode_fresh_proof_watch.ndjson`

## Reuse / Extend / Create Decision

- Existing capability reused: R149 watch prep, R142 watcher records, R146 post-bridge recheck, R126 first tiny-live lane gate, live-safety, binance-readonly-status.
- Existing capability extended: add a compact after-fresh-proof recheck/packet surface only if no existing command already composes the needed output.
- New capability created: only a thin R150 diagnostic packet/ledger if needed.
- Why new code is necessary: to summarize post-watch proof and gate state in one operator packet after fresh proof appears.
- Why this does not duplicate prior work: R150 must compose existing outputs and point to source records, not reimplement gates, safety checks, Binance checks, or proof capture.

## Duplicate Risk Report

- Similar existing modules: R146 post-bridge recheck, R149 watch prep, R126 first tiny-live lane execution gate, R102/R106 global gates.
- Similar existing endpoints: live-safety and binance-readonly status surfaces.
- Similar existing CLI commands: `post-bridge-watcher-proof-capture-recheck`, `first-tiny-live-lane-execution-gate`, `live-safety`, `binance-readonly-status`.
- Similar scheduler tasks: R142 watcher loop and lane autonomy scheduler.
- Similar docs: R146, R148, R149 live-readiness docs.
- Risk: HIGH.
- Mitigation: compose and cite existing surfaces; do not create a second readiness authority.

## Files Expected

Potential files:

- `src/app/hammer_radar/operator/after_fresh_proof_tiny_live_ready_recheck.py`
- `tests/hammer_radar/test_after_fresh_proof_tiny_live_ready_recheck.py`
- `docs/hammer_radar/live_readiness/R150_AFTER_FRESH_PROOF_TINY_LIVE_READY_RECHECK.md`
- update `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- update `src/app/hammer_radar/operator/inspect.py`

## Tests Required

- Recheck packet consumes fresh proof/watch records without creating proof.
- Tiny-live gates are rechecked for 13m and 44m.
- Live safety and Binance read-only summaries are included without order/account/order endpoint calls.
- Packet contains no live execution authorization.
- Wrong confirmation rejects any optional ledger write.
- Exact confirmation records packet only.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/after_fresh_proof_tiny_live_ready_recheck.py \
  src/app/hammer_radar/operator/inspect.py
```

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_after_fresh_proof_tiny_live_ready_recheck.py
```

## Safety Constraints

- No live execution unless explicitly authorized in a later phase.
- Do not place orders.
- Do not create executable order payloads.
- Do not create protective payloads.
- Do not call Binance order/test-order/protective endpoints.
- Do not call Binance account/order/private endpoints unless a future phase explicitly authorizes that exact read-only check.
- Do not create signed request material.
- Do not mutate env files.
- Do not mutate global live flags.
- Do not disable the global kill switch.
- Do not bypass R106/global gates.
- Do not create fake paper proof.

## Do Not

- Do not start the watcher.
- Do not run `live-connector-submit`.
- Do not run `sudo`.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not restart services.

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
- Runtime behavior changed:
- Safety result:
- Blockers, if any:
- Exact manual commands needed, if any:
