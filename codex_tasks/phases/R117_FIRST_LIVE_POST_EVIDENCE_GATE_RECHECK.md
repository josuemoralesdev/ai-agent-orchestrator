# R117 First-Live Post-Evidence Gate Recheck

## Phase

`R117`

## Branch

`r117-first-live-post-evidence-gate-recheck`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R116 can assist operator evidence recording group by group. R117 should run the post-evidence status and gate recheck sequence, determine whether R106 blockers were reduced, and keep the system non-executing.

## Assigned Agents

- builder: implement the non-executing recheck package
- index: map R112-R116 evidence and gate surfaces, then update the phase index
- qa: validate focused recheck tests plus relevant operator tests
- security: verify no execution authority, no Binance order calls, no env edits, and no secrets

## Main Objective

Add a non-executing post-evidence recheck command that runs evidence status after assisted recording, composes R113/R111/R110/R106/R109 rechecks, and reports whether R106 blockers reduced.

## Capability Scan

Inspect:
- `docs/hammer_radar/live_readiness/R112_FIRST_LIVE_OPERATOR_EVIDENCE_RECORDING.md`
- `docs/hammer_radar/live_readiness/R113_FIRST_LIVE_PREREQUISITE_RECHECK_AFTER_EVIDENCE.md`
- `docs/hammer_radar/live_readiness/R114_FIRST_LIVE_EVIDENCE_GUIDED_CLEARING_ACTIONS.md`
- `docs/hammer_radar/live_readiness/R115_FIRST_LIVE_EVIDENCE_RECORDING_RUNBOOK.md`
- `docs/hammer_radar/live_readiness/R116_FIRST_LIVE_EVIDENCE_RECORDING_ASSISTED_RUN.md`
- `src/app/hammer_radar/operator/first_live_operator_evidence.py`
- `src/app/hammer_radar/operator/first_live_prerequisite_recheck_after_evidence.py`
- `src/app/hammer_radar/operator/first_live_prerequisite_clearing.py`
- `src/app/hammer_radar/operator/first_live_burn_down.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/first_live_evidence_assisted_run.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R112 evidence status, R113 evidence recheck, R111 prerequisite clearing, R110 burn-down, R106 activation gate, R109 cockpit state, R116 assisted-run ledger
- Existing capability extended: inspect CLI only
- New capability created: thin post-evidence recheck/report module and ledger if needed
- Why new code is necessary: R117 needs one auditable post-R116 summary that compares blocker state after evidence recording without turning evidence into execution
- Why this does not duplicate prior work: it should compose existing status surfaces and avoid reimplementing their logic

## Duplicate Risk Report

- Similar existing modules: R113 recheck, R116 assisted run, R106 activation gate, R110 burn-down, R111 prerequisite clearing
- Similar existing endpoints: R109 cockpit state endpoints
- Similar existing CLI commands: `first-live-evidence-status`, `first-live-prerequisite-recheck-after-evidence`, `first-live-prerequisite-clearing`, `first-live-burn-down`, `first-live-activation-gate`, `first-live-evidence-assisted-run`
- Similar existing scheduler tasks: none expected
- Similar existing docs: R112-R116 live readiness docs
- Risk: HIGH
- Mitigation: compose existing modules, do not create a new gate, and keep R106 as authority

## Files Expected

- `src/app/hammer_radar/operator/first_live_post_evidence_gate_recheck.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/test_first_live_post_evidence_gate_recheck.py`
- `docs/hammer_radar/live_readiness/R117_FIRST_LIVE_POST_EVIDENCE_GATE_RECHECK.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`

## Tests Required

- evidence status is included after assisted recording
- R113/R111/R110/R106/R109 rechecks are included
- R106 blocker reduction is reported without changing R106 authority
- command remains non-executing
- no Binance order endpoint is called
- no live execution is enabled
- no env flags are modified
- secrets remain hidden
- paper/live separation remains intact
- ledger, if added, includes safety fields

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/first_live_post_evidence_gate_recheck.py src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_first_live_post_evidence_gate_recheck.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints unless explicitly authorized by a later phase.
- Do not modify env flags.
- Do not expose secrets.
- Do not weaken paper/live separation.
- Preserve human approval gates.
- Preserve kill-switch discipline.
- R106 remains first-live activation authority.
- R109 sacred button remains intent-only.
- Evidence recording is not execution authority.

## Do Not

- Do not run `sudo`.
- Do not attempt Git permission repair.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not restart production services.
- Do not create a live order endpoint.
- Do not wire evidence to execution.

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
