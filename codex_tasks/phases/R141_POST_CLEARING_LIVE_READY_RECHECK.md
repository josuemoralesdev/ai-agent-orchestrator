# R141 Post-Clearing Live-Ready Recheck

## Phase

`R141`

## Branch

`r141-post-clearing-live-ready-recheck`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R140 safely executes the non-live subset of the R139 clearing pack and records a
before/after run ledger. R141 must re-run the live-readiness gates after that
clearing evidence and decide whether the lane is still blocked or whether the
next explicit operator action should be lane-mode tiny_live authorization
planning.

## Assigned Agents

- builder: implement the recheck wrapper and tests
- index: map reused R138/R139/R140/R126/R130/R131/R132/R134/R136/R137 surfaces
- qa: validate no writes except the R141 diagnostic ledger
- security: verify no live execution, Binance calls, payload creation, signing, env mutation, or config mutation

## Main Objective

Create a post-R140 read-only recheck that compares R138, R139, and R140
before/after evidence, reruns all relevant gates, reports updated blocker
movement, and produces an updated tiny-live probability.

## Required Behavior

- No real orders.
- No Binance calls.
- No order payloads.
- No protective payloads.
- No signed requests.
- No env or lane config mutation.
- Rerun R138 burn-down, R139 operator pack, R140 run summary, R126 gate, R130
  authorization preview, R131 kill-switch rehearsal, R132 adapter boundary,
  R134 dry authorization, R136 protective policy, and R137 protective preview.
- Compare latest R140 before/after with current recheck.
- Decide whether lane mode tiny_live authorization is the next explicit operator
  action or whether the lane remains blocked.
- Produce updated live probability.

## Expected Artifact

- `src/app/hammer_radar/operator/post_clearing_live_ready_recheck.py`
- `docs/hammer_radar/live_readiness/R141_POST_CLEARING_LIVE_READY_RECHECK.md`
- `tests/hammer_radar/test_post_clearing_live_ready_recheck.py`
- Optional append-only diagnostic ledger:
  `logs/hammer_radar_forward/post_clearing_live_ready_rechecks.ndjson`

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/post_clearing_live_ready_recheck.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_post_clearing_live_ready_recheck.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order or test-order endpoints.
- Do not call protective order endpoints.
- Do not create executable or protective payloads.
- Do not create signed request material.
- Do not mutate env files or lane config.
- Do not disable the global kill switch.
- Do not commit, merge, tag, push, deploy, install services, restart services, or run `sudo`.
