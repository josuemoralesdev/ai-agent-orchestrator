# R116 First-Live Evidence Recording Assisted Run

## Phase

`R116`

## Branch

`r116-first-live-evidence-recording-assisted-run`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R115 creates a safe first-live evidence recording runbook and command pack. R116 should provide an assisted operator run that lets the operator choose which R115 evidence sections to record while preserving all non-execution boundaries.

## Assigned Agents

- builder: implement the assisted run surface only if needed, reusing R115/R114/R112.
- index: preserve R106 authority, R109 intent-only semantics, and phase index/source-of-truth boundaries.
- qa: validate selected-section behavior and safety booleans.
- security: verify no order placement, no Binance order endpoints, no env flag edits, and no secret exposure.

## Main Objective

Create an assisted evidence-recording run phase where the operator chooses which R115 evidence sections to record. Commands may be printed, or optionally run only after explicit user authorization in the current turn.

## Capability Scan

Inspect:
- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `docs/hammer_radar/live_readiness/R112_FIRST_LIVE_OPERATOR_EVIDENCE_RECORDING.md`
- `docs/hammer_radar/live_readiness/R113_FIRST_LIVE_PREREQUISITE_RECHECK_AFTER_EVIDENCE.md`
- `docs/hammer_radar/live_readiness/R114_FIRST_LIVE_EVIDENCE_GUIDED_CLEARING_ACTIONS.md`
- `docs/hammer_radar/live_readiness/R115_FIRST_LIVE_EVIDENCE_RECORDING_RUNBOOK.md`
- `src/app/hammer_radar/operator/first_live_operator_evidence.py`
- `src/app/hammer_radar/operator/first_live_prerequisite_recheck_after_evidence.py`
- `src/app/hammer_radar/operator/first_live_evidence_guided_actions.py`
- `src/app/hammer_radar/operator/first_live_evidence_runbook.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R115 runbook, R114 evidence command generation, R112 evidence recording, R113 recheck, R111/R110/R106/R109 recheck sequence.
- Existing capability extended: assisted operator selection and optional explicitly authorized command execution only.
- New capability created: only the assisted run wrapper if required.
- Why new code is necessary: R115 only builds the runbook; R116 can coordinate selected sections.
- Why this does not duplicate prior work: R116 must consume R115/R114 outputs instead of regenerating evidence commands or readiness logic.

## Required Behavior

R116 should:
- list R115 sections available for recording
- let the operator choose one or more evidence sections
- print commands by default
- optionally run selected evidence commands only after explicit user authorization in the current turn
- run R112/R113/R111/R110/R106/R109 rechecks after each selected group when execution is explicitly authorized
- preserve R106 as authority
- preserve R109 sacred button as intent-only
- record an audit ledger for assisted-run decisions

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
- Do not run commands unless the operator explicitly authorizes that exact action in the current turn.

## Tests Required

Add focused tests proving:
- default mode prints commands only
- selected sections are honored
- unauthorized runs do not execute commands
- authorized runs still only call R112/R113/R111/R110/R106/R109 surfaces
- no order placement occurs
- no execution attempt occurs
- no Binance order endpoint appears
- no env flag edits occur
- secrets are not exposed
- R106 remains authority
- R109 remains intent-only

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile <modified-python-files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused-r116-tests>
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
