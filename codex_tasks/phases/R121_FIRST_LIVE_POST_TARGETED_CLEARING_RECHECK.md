# R121 First-Live Post-Targeted Clearing Recheck

## Phase

`R121`

## Branch

`r121-first-live-post-targeted-clearing-recheck`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R120 produces a targeted clearing pack over R119 lanes. After the operator records only personally verified evidence through R116/R112, R121 must recheck whether blockers moved and decide the next safe non-executing step.

## Assigned Agents

- builder: implement only the R121 recheck/report surface
- index: verify reuse of R112/R116/R117/R118/R119/R120 and update phase indexes
- qa: validate safety fields, ledgers, and CLI behavior
- security: enforce no execution, no secrets, no Binance order calls, and no env changes

## Main Objective

Recheck evidence after the operator uses R120/R116 commands, then decide:

1. If R118 remains blocked, produce the next targeted R119/R120 clearing lane.
2. If R118 moved closer to ready, report remaining blockers and required evidence.
3. If R118 says `READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION`, prepare an explicit authorization request phase artifact.

R121 must remain non-executing unless a later phase and current-turn instruction explicitly authorize execution.

## Capability Scan

Inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R120_FIRST_LIVE_TARGETED_CLEARING_PACK.md`
- `docs/hammer_radar/live_readiness/R119_FIRST_LIVE_BLOCKER_CLEARING_WORKBENCH.md`
- `docs/hammer_radar/live_readiness/R118_FIRST_LIVE_ACTIVATION_GATE_FINAL_REVIEW.md`
- `docs/hammer_radar/live_readiness/R117_FIRST_LIVE_POST_EVIDENCE_GATE_RECHECK.md`
- `src/app/hammer_radar/operator/first_live_targeted_clearing_pack.py`
- `src/app/hammer_radar/operator/first_live_blocker_clearing_workbench.py`
- `src/app/hammer_radar/operator/first_live_activation_gate_final_review.py`
- `src/app/hammer_radar/operator/first_live_post_evidence_gate_recheck.py`
- `src/app/hammer_radar/operator/first_live_evidence_assisted_run.py`
- `src/app/hammer_radar/operator/first_live_operator_evidence.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`
- relevant ledgers under `logs/hammer_radar_forward/`

## Reuse / Extend / Create Decision

- Existing capability reused: R120 targeted clearing pack, R119 workbench, R118 final review, R117 post-evidence recheck, R112/R116 evidence surfaces, R106 activation gate, R109 cockpit.
- Existing capability extended: only a thin R121 recheck/report layer if needed.
- New capability created: only for R121 diagnostic output and optional authorization-request preparation artifact.
- Why new code is necessary: R121 must compare post-targeted-clearing state after operator evidence recording and decide the next non-executing path.
- Why this does not duplicate prior work: R121 must consume existing surfaces and avoid recomputing readiness from scratch.

## Duplicate Risk Report

- Similar existing modules: R120 targeted clearing pack, R119 workbench, R118 final review, R117 post-evidence recheck.
- Similar existing endpoints: R109 approval cockpit state and intent endpoints.
- Similar existing CLI commands: `first-live-targeted-clearing-pack`, `first-live-blocker-clearing-workbench`, `first-live-activation-final-review`, `first-live-post-evidence-gate-recheck`, `first-live-evidence-assisted-run`.
- Similar scheduler tasks: none expected.
- Similar docs: R112-R120 live-readiness docs.
- Risk: HIGH.
- Mitigation: consume R120/R119/R118/R117 outputs; do not create a second activation gate, evidence ledger, authorization authority, cockpit, or execution path.

## Files Expected

- R121 operator module if a new diagnostic report is necessary
- `src/app/hammer_radar/operator/inspect.py`
- R121 tests under `tests/hammer_radar/`
- R121 live-readiness doc
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`

## Tests Required

Cover:

- R121 returns `live_ready=false`
- R121 returns execution disabled
- R121 never places orders
- R121 never exposes secrets
- R121 rechecks R112/R113/R117/R119/R118/R106/R109 after targeted clearing
- R121 returns the next targeted lane when R118 remains blocked
- R121 reports authorization preparation only when R118 says `READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION`
- R121 does not request authorization while R118 is blocked
- ledger write contains hard safety fields
- paper/live separation remains intact

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
- R106 remains authority.
- R109 remains intent-only.

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
- Selected R121 path:
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
