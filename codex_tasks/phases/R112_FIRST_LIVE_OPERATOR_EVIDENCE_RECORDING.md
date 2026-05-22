# R112 First-Live Operator Evidence Recording

## Phase

`R112`

## Branch

`r112-first-live-operator-evidence-recording`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R111 turns the R110 burn-down groups into explicit prerequisite checks and identifies the groups that need operator evidence. R112 should add safe evidence-recording helpers for those missing records without placing orders or creating execution authority.

## Assigned Agents

- builder: implement scoped evidence-recording helpers only where existing surfaces do not already provide them.
- index: preserve R102-R111 source-of-truth boundaries and update live-readiness indexes.
- qa: verify records are append-only, safety booleans stay false, and no execution side effects occur.
- security: enforce no live order placement, no Binance order calls, no env flag edits, and no secret exposure.

## Main Objective

Record missing first-live operator evidence/checklists safely so R111 prerequisite groups can move from `NEEDS_OPERATOR_EVIDENCE` toward `CLEAR` without creating execution authority.

## Capability Scan

Inspect:
- `AGENTS.md`
- `AGENTS.builder.md`
- `AGENTS.index.md`
- `AGENTS.qa.md`
- `AGENTS.security.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `docs/hammer_radar/live_readiness/R102_ONE_COMMAND_FINAL_PREFLIGHT.md`
- `docs/hammer_radar/live_readiness/R103_TELEGRAM_FINAL_APPROVAL_FLOW.md`
- `docs/hammer_radar/live_readiness/R104_TINY_LIVE_ARMED_DRY_RUN.md`
- `docs/hammer_radar/live_readiness/R105_ONE_TINY_LIVE_ORDER_PROTOCOL.md`
- `docs/hammer_radar/live_readiness/R106_FIRST_LIVE_ACTIVATION_GATE.md`
- `docs/hammer_radar/live_readiness/R109_FIRST_LIVE_COCKPIT_SACRED_BUTTON_HARDENING.md`
- `docs/hammer_radar/live_readiness/R110_FIRST_LIVE_READINESS_BURN_DOWN_PACK.md`
- `docs/hammer_radar/live_readiness/R111_FIRST_LIVE_ACTIVATION_PREREQUISITE_CLEARING.md`
- `src/app/hammer_radar/operator/first_live_prerequisite_clearing.py`
- existing approval, review, funding, protective, and risk contract record modules
- `tests/hammer_radar/`
- `configs/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R103 approval intent, R85/R86/R88 human review records, R102/R104/R105/R106/R109/R110/R111 readiness reports.
- Existing capability extended: only add evidence-recording fields or adapters where current record surfaces do not capture R111 evidence needs.
- New capability created: small append-only evidence records only if no existing ledger fits.
- Why new code is necessary: R111 can identify missing evidence, but missing operator evidence needs a safe structured place to be recorded.
- Why this does not duplicate prior work: R112 should record evidence consumed by existing readiness surfaces rather than create another gate.

## Evidence Scope

R112 should focus on:
- approval intent evidence
- human review evidence
- read-only funding evidence
- protective readiness evidence
- tiny size evidence
- max loss evidence

## Explicit Non-Scope

R112 must not:
- place a live order
- enable live trading
- call Binance order endpoints
- call Binance account or balance endpoints unless a read-only procedure is explicitly approved in the future task
- modify env flags
- wire approval buttons to execution
- create execution authority
- create a live order endpoint
- expose secrets
- run `sudo`
- commit, merge, tag, push, deploy, or restart services

No live order placement is allowed unless separately explicitly authorized later.

## Tests Required

Add focused tests proving:
- evidence records are append-only
- safety booleans remain false
- no order is placed
- execution is not attempted
- secrets are not shown
- R106 remains the activation authority
- R109 sacred button remains intent-only
- R111 can consume the recorded evidence where applicable
- paper/live separation stays intact

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile <modified-python-files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused-r112-tests>
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not modify env flags.
- Do not expose secrets.
- Do not weaken paper/live separation.
- Preserve human approval gates.
- Preserve kill-switch discipline.

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
