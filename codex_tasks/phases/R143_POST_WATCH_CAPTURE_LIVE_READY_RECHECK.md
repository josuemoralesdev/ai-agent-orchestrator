# R143 Post-Watch Capture Live-Ready Recheck

## Phase

`R143`

## Branch

`r143-post-watch-capture-live-ready-recheck`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Reason

R142 can either capture fresh autonomous paper proof through R140/R129 or time out safely with no eligible candidate. R143 should compare the before/after proof state and decide the next non-executing operator move for the 13m and 44m candidate lanes.

## Main Objective

Build a post-R142 recheck that consumes R142 watcher records, R129/R140 paper proof state, R141 post-clearing recheck output, and existing tiny-live lane authorization surfaces to update live-readiness odds without placing orders or calling Binance.

## Required Behavior

- No real orders.
- No Binance calls.
- No Binance test-order calls.
- No protective order calls.
- No executable order payloads.
- No protective payloads.
- No signed requests.
- No env mutation.
- No lane config mutation.
- No live flag changes.
- No kill-switch changes.
- Compare R142 watcher outcome against current R129/R140/R141/R138 state.
- If proof was captured, re-evaluate tiny-live lane authorization readiness for:
  - `BTCUSDT|13m|long|ladder_close_50_618`
  - `BTCUSDT|44m|long|ladder_close_50_618`
- If R142 timed out, recommend the next bounded watch window and watched lanes.
- Update live odds using existing R138/R141 probability summaries; do not invent a new readiness authority.

## Capability Scan

Inspect before implementation:

- `src/app/hammer_radar/operator/fresh_candidate_paper_proof_capture_loop.py`
- `src/app/hammer_radar/operator/post_clearing_live_ready_recheck.py`
- `src/app/hammer_radar/operator/operator_executes_safe_clearing_pack.py`
- `src/app/hammer_radar/operator/autonomous_paper_lane_executor_integration.py`
- `src/app/hammer_radar/operator/autonomous_lane_live_ready_burn_down.py`
- `src/app/hammer_radar/operator/first_tiny_live_lane_execution_gate.py`
- `src/app/hammer_radar/operator/first_tiny_live_autonomous_lane_authorization.py`
- `tests/hammer_radar/test_fresh_candidate_paper_proof_capture_loop.py`
- `docs/hammer_radar/live_readiness/R142_FRESH_CANDIDATE_PAPER_PROOF_CAPTURE_LOOP.md`

## Expected Files

- `src/app/hammer_radar/operator/post_watch_capture_live_ready_recheck.py`
- `tests/hammer_radar/test_post_watch_capture_live_ready_recheck.py`
- `docs/hammer_radar/live_readiness/R143_POST_WATCH_CAPTURE_LIVE_READY_RECHECK.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order, test-order, protective, account, balance, or private endpoints.
- Do not create executable or protective payloads.
- Do not create signed request material.
- Do not mutate env files or lane config.
- Do not disable the global kill switch.
- Do not install/start services.
- Do not run `sudo`.
- Do not commit, merge, tag, push, or deploy.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/post_watch_capture_live_ready_recheck.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_post_watch_capture_live_ready_recheck.py
```
