# R113 First-Live Prerequisite Recheck After Evidence

## Phase

`R113`

## Branch

`r113-first-live-prerequisite-recheck-after-evidence`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R112 records append-only operator evidence for the prerequisite needs identified by R111. R113 should re-run prerequisite clearing using that recorded evidence and determine whether R106 blockers reduce for the same candidate, risk contract hash, and packet hash tuple.

## Assigned Agents

- builder: wire R112 evidence into R111-style prerequisite recheck without creating execution authority.
- index: preserve R102-R112 source-of-truth boundaries and update live-readiness indexes.
- qa: prove the recheck remains non-executing and only changes diagnostic/prerequisite status.
- security: verify no Binance order/account calls, no env edits, no secret exposure, and no approval-to-execution wiring.

## Main Objective

Add a non-executing prerequisite recheck that consumes `first_live_operator_evidence.ndjson`, compares accepted evidence against R111 prerequisite groups, and reports whether R106 blockers are reduced.

## Capability Scan

Inspect:
- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `docs/hammer_radar/live_readiness/R111_FIRST_LIVE_ACTIVATION_PREREQUISITE_CLEARING.md`
- `docs/hammer_radar/live_readiness/R112_FIRST_LIVE_OPERATOR_EVIDENCE_RECORDING.md`
- `src/app/hammer_radar/operator/first_live_prerequisite_clearing.py`
- `src/app/hammer_radar/operator/first_live_operator_evidence.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/inspect.py`
- existing approval/review ledgers
- `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R111 prerequisite groups, R112 evidence ledger/status, R106 activation gate output.
- Existing capability extended: add a recheck adapter and inspect command only if needed.
- New capability created: no new gate; only a recheck report/ledger if useful.
- Why new code is necessary: R111 does not currently consume R112 evidence.
- Why this does not duplicate prior work: R113 should compare existing prerequisite output with recorded evidence rather than recomputing readiness independently.

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call Binance account, funding, balance, or position endpoints.
- Do not modify env flags.
- Do not wire evidence to execution.
- Do not create execution authority.
- Do not create a live order endpoint.
- Do not expose secrets.
- R106 remains first-live activation authority.
- R109 remains intent-only.

## Expected Behavior

R113 should report:
- current R111 prerequisite status
- current R112 evidence status
- matching candidate/hash tuple
- prerequisite groups whose evidence can now be considered present
- prerequisite groups still blocked
- whether R106 blockers reduced
- `live_ready=false`
- `execution_enabled_by_recheck=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## Tests Required

Add focused tests proving:
- no ledger means no prerequisite reduction
- partial evidence does not clear all evidence-needed groups
- complete accepted evidence for one tuple can mark evidence-backed groups ready for R111/R106 recheck
- mixed tuples do not clear evidence
- rejected evidence does not clear evidence
- safety booleans remain false
- no order is placed
- no Binance endpoints are called
- secrets are not exposed

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile <modified-python-files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused-r113-tests>
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Do Not

- Do not run `sudo`.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not restart services.
