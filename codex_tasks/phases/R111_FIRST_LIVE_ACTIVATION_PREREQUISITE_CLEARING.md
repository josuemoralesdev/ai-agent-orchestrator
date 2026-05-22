# R111 First-Live Activation Prerequisite Clearing

## Phase

`R111`

## Branch

`r111-first-live-activation-prerequisite-clearing`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R110 converts the R102-R109 blocker wall into a prioritized burn-down pack. R111 should clear prerequisite blockers for `FIRST_LIVE_ACTIVATION_READY` without placing orders or creating execution authority.

## Assigned Agents

- builder: implement prerequisite-clearing adapters or records only where existing surfaces need small wiring.
- index: preserve R102-R109 source-of-truth boundaries and update live-readiness indexes.
- qa: verify safety booleans, append-only records, and focused readiness commands.
- security: enforce no live order placement, no Binance order calls, no env flag edits, and no secret exposure.

## Main Objective

Clear or convert the R110 top blockers into auditable prerequisite records for a future `FIRST_LIVE_ACTIVATION_READY` attempt. R111 is not order placement.

## Capability Scan

Inspect:
- `AGENTS.md`
- `AGENTS.builder.md`
- `AGENTS.index.md`
- `AGENTS.qa.md`
- `AGENTS.security.md`
- `codex_tasks/CODEX_RULES.md`
- `codex_tasks/agents/AGENT_WORKFLOW.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `docs/hammer_radar/live_readiness/R102_ONE_COMMAND_FINAL_PREFLIGHT.md`
- `docs/hammer_radar/live_readiness/R103_TELEGRAM_FINAL_APPROVAL_FLOW.md`
- `docs/hammer_radar/live_readiness/R104_TINY_LIVE_ARMED_DRY_RUN.md`
- `docs/hammer_radar/live_readiness/R105_ONE_TINY_LIVE_ORDER_PROTOCOL.md`
- `docs/hammer_radar/live_readiness/R106_FIRST_LIVE_ACTIVATION_GATE.md`
- `docs/hammer_radar/live_readiness/R109_FIRST_LIVE_COCKPIT_SACRED_BUTTON_HARDENING.md`
- `docs/hammer_radar/live_readiness/R110_FIRST_LIVE_READINESS_BURN_DOWN_PACK.md`
- `src/app/hammer_radar/operator/final_live_preflight.py`
- `src/app/hammer_radar/operator/final_approval_intent.py`
- `src/app/hammer_radar/operator/tiny_live_armed_dry_run.py`
- `src/app/hammer_radar/operator/one_tiny_live_order_protocol.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/first_live_burn_down.py`
- `src/app/hammer_radar/operator/inspect.py`
- `src/app/hammer_radar/execution/`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/first_live_execution_design_checklist.json`
- `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R102 final preflight, R103 approval intent, R104 dry-run, R105 protocol, R106 activation gate, R109 cockpit state, R110 burn-down report.
- Existing capability extended: only if a prerequisite record or read-only review adapter is missing.
- New capability created: only small prerequisite-clearing records/checks that do not already exist.
- Why new code is necessary: only to make prerequisite evidence explicit and auditable when current surfaces report manual unknowns.
- Why this does not duplicate prior work: R111 must consume R110 group outputs and existing gate surfaces rather than creating a new readiness gate.

## Duplicate Risk Report

- Similar existing modules: final preflight, approval intent, armed dry run, one tiny protocol, activation gate, cockpit, burn-down.
- Similar existing endpoints: `/operator/approval-cockpit/state`, existing readiness and first-live review endpoints.
- Similar existing CLI commands: `final-live-preflight`, `tiny-live-armed-dry-run`, `one-tiny-live-order-protocol`, `first-live-activation-gate`, `first-live-burn-down`.
- Similar existing scheduler tasks: none expected for R111.
- Similar existing docs: R102-R110 live-readiness docs.
- Risk: HIGH.
- Mitigation: extend or record against existing source surfaces. Do not create a second activation gate.

## Scope To Clear

R111 may clear or prepare auditable evidence for:
- approval records
- environment review
- protective readiness
- candidate freshness
- account/funding verification
- final preflight consistency
- sacred button state review

## Explicit Non-Scope

R111 must not:
- place a live order
- enable live trading
- call Binance order endpoints
- modify env flags
- wire approval buttons to execution
- create execution authority
- create a live order endpoint
- expose secrets
- run `sudo`
- commit, merge, tag, push, deploy, or restart services

No live order placement is allowed unless explicitly authorized in a later phase.

## Tests Required

Add focused tests proving:
- R111 records/checks stay prerequisite-only
- `live_ready` remains false unless the existing R106 contract explicitly defines otherwise
- no order is placed
- execution is not attempted
- secrets are not shown
- R106 remains the activation authority
- R109 sacred button remains intent-only
- paper/live separation stays intact

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile <modified-python-files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused-r111-tests>
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints unless explicitly authorized in R111.
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
