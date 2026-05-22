# R115 First-Live Evidence Recording Runbook

## Phase

`R115`

## Branch

`r115-first-live-evidence-recording-runbook`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R114 generates exact evidence-recording commands for the active candidate/hash tuple. R115 should turn that generated action pack into an operator runbook for recording only personally verified evidence and then rerunning the non-executing R112/R113/R111/R106 chain.

## Assigned Agents

- builder: create the operator runbook and any small inspect/report adapter only if needed.
- index: preserve R106 authority, R109 intent-only status, and phase index/source-of-truth boundaries.
- qa: validate that the runbook remains non-executing and uses R114-generated commands safely.
- security: verify no Binance calls, no env edits, no secret exposure, and no execution authority.

## Main Objective

Create an operator runbook for using R114 generated commands to record first-live evidence, then rerun R112 status, R113 recheck, R111 prerequisite clearing, and R106 activation gate.

## Capability Scan

Inspect:
- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `docs/hammer_radar/live_readiness/R112_FIRST_LIVE_OPERATOR_EVIDENCE_RECORDING.md`
- `docs/hammer_radar/live_readiness/R113_FIRST_LIVE_PREREQUISITE_RECHECK_AFTER_EVIDENCE.md`
- `docs/hammer_radar/live_readiness/R114_FIRST_LIVE_EVIDENCE_GUIDED_CLEARING_ACTIONS.md`
- `src/app/hammer_radar/operator/first_live_operator_evidence.py`
- `src/app/hammer_radar/operator/first_live_prerequisite_recheck_after_evidence.py`
- `src/app/hammer_radar/operator/first_live_evidence_guided_actions.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R114 action pack, R112 evidence recording/status, R113 recheck, R111 prerequisite clearing, R106 activation gate, R109 cockpit state.
- Existing capability extended: documentation/runbook surfaces only unless a small report command is necessary.
- New capability created: operator runbook artifact for evidence recording procedure.
- Why new code is necessary: only if the runbook needs a machine-readable checklist view over R114 output.
- Why this does not duplicate prior work: R115 should instruct how to use R114; it should not regenerate readiness logic or evidence commands independently.

## Required Behavior

R115 should include:
- active tuple verification step
- instruction to run R114 first and inspect `tuple_status`
- instruction to record only evidence the operator personally verified
- warning not to paste secret values or credentials into notes
- ordered evidence-recording procedure using R114 generated commands
- exact recheck sequence:
  1. `first-live-evidence-status`
  2. `first-live-prerequisite-recheck-after-evidence`
  3. `first-live-prerequisite-clearing`
  4. `first-live-burn-down`
  5. `first-live-activation-gate`
  6. cockpit state curl
- stop conditions for tuple mismatch, rejected evidence, blockers remaining, or unsafe sacred button state
- explicit statement that `FIRST_LIVE_ACTIVATION_READY` is not order execution authority

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call Binance account, funding, balance, or position endpoints unless explicitly authorized in a later phase.
- Do not modify env flags.
- Do not wire evidence to execution.
- Do not create execution authority.
- Do not create a live order endpoint.
- Do not expose secrets.
- R106 remains authority.
- R109 sacred button remains intent-only.
- R115 remains non-executing unless explicitly authorized later.

## Tests Required

If runtime code is added, add focused tests proving:
- the runbook/report returns `live_ready=false`
- no order placement or execution attempt is possible
- generated/manual commands are R112/R113/R111/R110/R106/cockpit state only
- no secret-like placeholder content is emitted in notes
- R106 remains authority and R109 remains intent-only

Documentation-only validation:

```bash
git diff --check
```

Runtime validation if code is added:

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <modified-python-files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused-r115-tests>
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
