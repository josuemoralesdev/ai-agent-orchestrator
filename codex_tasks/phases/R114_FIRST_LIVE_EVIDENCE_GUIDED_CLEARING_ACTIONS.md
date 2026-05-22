# R114 First-Live Evidence-Guided Clearing Actions

## Phase

`R114`

## Branch

`r114-first-live-evidence-guided-clearing-actions`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R113 reports which R111 prerequisite groups remain blocked or need more R112 evidence. R114 should turn those gaps into exact operator commands for the active candidate/hash tuple while preserving the non-executing first-live path.

## Assigned Agents

- builder: add guided command generation over R113/R112/R111 without creating execution authority.
- index: preserve R106 authority, R109 intent-only cockpit state, and phase index/source-of-truth boundaries.
- qa: prove generated commands remain evidence/recheck commands only and never place orders.
- security: verify no Binance order/account calls, no env edits, no secret exposure, and no evidence-to-execution wiring.

## Main Objective

Generate exact record-first-live-evidence commands for missing R113 evidence groups and an exact safe recheck sequence for the active tuple.

## Capability Scan

Inspect:
- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `docs/hammer_radar/live_readiness/R111_FIRST_LIVE_ACTIVATION_PREREQUISITE_CLEARING.md`
- `docs/hammer_radar/live_readiness/R112_FIRST_LIVE_OPERATOR_EVIDENCE_RECORDING.md`
- `docs/hammer_radar/live_readiness/R113_FIRST_LIVE_PREREQUISITE_RECHECK_AFTER_EVIDENCE.md`
- `src/app/hammer_radar/operator/first_live_prerequisite_clearing.py`
- `src/app/hammer_radar/operator/first_live_operator_evidence.py`
- `src/app/hammer_radar/operator/first_live_prerequisite_recheck_after_evidence.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/inspect.py`
- existing approval/review ledgers
- `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R113 blocker recheck, R112 evidence recording/status, R111 prerequisite groups, R106 activation command, R109 cockpit state command.
- Existing capability extended: add a guided clearing action adapter and inspect command only if needed.
- New capability created: no new gate; only a command-generation report/ledger if useful.
- Why new code is necessary: R113 reports gaps but does not generate complete copy-paste evidence commands.
- Why this does not duplicate prior work: R114 should consume R113 output and generate safe operator actions rather than recomputing readiness.

## Required Behavior

Add a non-executing guided clearing command that returns:
- active tuple used for evidence
- missing evidence by R113 group
- exact `record-first-live-evidence` commands for the tuple
- exact R112 status command
- exact R113 recheck command
- exact R106 recheck command
- cockpit state command
- safety booleans proving no execution path was created

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

## Tests Required

Add focused tests proving:
- generated commands are only evidence/recheck commands
- no generated command calls execution or Binance order surfaces
- no live flag modification command is generated
- missing evidence creates exact record-first-live-evidence commands for the active tuple
- complete evidence produces only the recheck sequence
- safety booleans remain false
- secrets are not exposed

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile <modified-python-files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused-r114-tests>
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
