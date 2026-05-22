# R120 First-Live Targeted Clearing Or Authorization Request

## Phase

`R120`

## Branch

`r120-first-live-targeted-clearing-or-authorization-request`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R119 organizes the R118 blocker wall into clearing lanes. R120 must choose the next safe path from the latest R119/R118 state without creating execution authority.

## Assigned Agents

- builder: implement only the selected R120 path
- index: verify source-of-truth reuse and update phase indexes
- qa: validate safety fields, ledgers, and CLI behavior
- security: enforce no execution, no secrets, no Binance order calls, and no env changes

## Main Objective

Choose exactly one path:

1. Targeted clearing for the highest remaining R119 lane if R118 remains blocked.
2. Explicit authorization request preparation if R118 becomes ready.

R120 remains non-executing by default. It must not place orders or enable live trading.

## Capability Scan

Inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R119_FIRST_LIVE_BLOCKER_CLEARING_WORKBENCH.md`
- `docs/hammer_radar/live_readiness/R118_FIRST_LIVE_ACTIVATION_GATE_FINAL_REVIEW.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `src/app/hammer_radar/operator/first_live_blocker_clearing_workbench.py`
- `src/app/hammer_radar/operator/first_live_activation_gate_final_review.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/first_live_evidence_assisted_run.py`
- `src/app/hammer_radar/operator/first_live_operator_evidence.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`
- relevant ledgers under `logs/hammer_radar_forward/`

## Reuse / Extend / Create Decision

- Existing capability reused: R119 workbench, R118 final review, R106 activation gate, R109 cockpit, R112/R116 evidence surfaces.
- Existing capability extended: only if R120 needs a thin CLI/report layer over the selected path.
- New capability created: only for the chosen R120 diagnostic output or authorization-request preparation artifact.
- Why new code is necessary: only if current R119 output cannot represent the selected targeted clearing or authorization-request preparation.
- Why this does not duplicate prior work: R120 must consume R119/R118 rather than recompute readiness from scratch.

## Duplicate Risk Report

- Similar existing modules: R119 workbench, R118 final review, R117 post-evidence recheck, R116 assisted run.
- Similar existing endpoints: R109 approval cockpit state and intent endpoints.
- Similar existing CLI commands: `first-live-blocker-clearing-workbench`, `first-live-activation-final-review`, `first-live-activation-gate`, `first-live-evidence-assisted-run`.
- Similar scheduler tasks: none expected.
- Similar docs: R112-R119 live-readiness docs.
- Risk: HIGH.
- Mitigation: extend or consume existing surfaces; do not create a second activation gate, second evidence ledger, second cockpit, or execution path.

## Files Expected

To be decided by the selected path. Likely candidates:

- R120 operator module if a new diagnostic report is necessary
- `src/app/hammer_radar/operator/inspect.py`
- R120 tests under `tests/hammer_radar/`
- R120 live-readiness doc
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`

## Tests Required

Cover:

- selected path is derived from current R119/R118 state
- live_ready remains false
- execution remains disabled
- order_placed remains false
- execution_attempted remains false
- real_order_possible remains false
- secrets_shown remains false
- R106 remains authority
- R109 remains intent-only
- no env flag edits
- no Binance order endpoint calls
- append-only ledger behavior if a new ledger is added

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile <modified_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused_tests>
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints unless explicitly authorized.
- Do not modify env flags.
- Do not expose secrets.
- Do not weaken paper/live separation.
- Preserve human approval gates.
- Preserve kill-switch discipline.
- R120 must remain non-executing unless a later current-turn instruction explicitly authorizes execution.

## Do Not

- Do not run `sudo`.
- Do not attempt Git permission repair.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not restart production services.
- Do not modify unrelated files.

## Final Report Format

Report:

- Branch:
- Selected R120 path:
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
