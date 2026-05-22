# R118 First-Live Activation Gate Final Review

## Phase

`R118`

## Branch

`r118-first-live-activation-gate-final-review`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R117 creates the post-evidence gate recheck package after R112/R116 evidence recording. R118 should perform the final non-executing activation-gate review and determine whether the system is ready to request explicit first-live execution authorization in a later phase.

## Assigned Agents

- builder: implement the final review package without execution authority
- index: verify R106 remains the authority and update live-readiness indexes
- qa: validate final review status, safety fields, and ledger behavior
- security: verify no order calls, no env edits, no secrets, and no approval-to-execution wiring

## Main Objective

Add a non-executing final activation-gate review after R117 that reviews R117, R106, R109, and remaining blockers to decide whether the operator can request explicit first-live execution authorization later.

## Capability Scan

Inspect:
- `docs/hammer_radar/live_readiness/R106_FIRST_LIVE_ACTIVATION_GATE.md`
- `docs/hammer_radar/live_readiness/R109_FIRST_LIVE_COCKPIT_SACRED_BUTTON_HARDENING.md`
- `docs/hammer_radar/live_readiness/R112_FIRST_LIVE_OPERATOR_EVIDENCE_RECORDING.md`
- `docs/hammer_radar/live_readiness/R113_FIRST_LIVE_PREREQUISITE_RECHECK_AFTER_EVIDENCE.md`
- `docs/hammer_radar/live_readiness/R116_FIRST_LIVE_EVIDENCE_RECORDING_ASSISTED_RUN.md`
- `docs/hammer_radar/live_readiness/R117_FIRST_LIVE_POST_EVIDENCE_GATE_RECHECK.md`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/first_live_post_evidence_gate_recheck.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R117 post-evidence recheck, R106 activation gate, R109 cockpit sacred-button state
- Existing capability extended: inspect CLI only if a command is added
- New capability created: thin final review/report module and ledger if needed
- Why new code is necessary: R118 needs a final auditable review package before any later explicit execution-authorization request
- Why this does not duplicate prior work: it should summarize existing gate authority and R117 evidence delta without replacing R106

## Duplicate Risk Report

- Similar existing modules: R106 activation gate, R109 cockpit, R117 post-evidence recheck
- Similar existing endpoints: R109 cockpit state endpoints
- Similar existing CLI commands: `first-live-activation-gate`, `first-live-post-evidence-gate-recheck`
- Similar existing scheduler tasks: none expected
- Similar existing docs: R106/R109/R117 live readiness docs
- Risk: HIGH
- Mitigation: compose existing modules, do not create execution authority, and keep R106 as the activation authority

## Files Expected

- `src/app/hammer_radar/operator/first_live_activation_gate_final_review.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/test_first_live_activation_gate_final_review.py`
- `docs/hammer_radar/live_readiness/R118_FIRST_LIVE_ACTIVATION_GATE_FINAL_REVIEW.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`

## Tests Required

- R118 returns `live_ready=false`
- R118 returns execution enablement false
- R118 never places orders
- R118 never exposes secrets
- R118 includes R117, R106, and R109 source statuses
- R118 blocks if R117 is not ready for activation-gate recheck
- R118 blocks if R106 is blocked
- R118 blocks if R109 sacred button can place orders
- R118 blocks if paper/live separation is false
- R118 ledger includes safety fields

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/first_live_activation_gate_final_review.py src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_first_live_activation_gate_final_review.py
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
- R118 is non-executing unless a later phase explicitly authorizes execution.

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
- Do not wire approval or evidence to execution.

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
