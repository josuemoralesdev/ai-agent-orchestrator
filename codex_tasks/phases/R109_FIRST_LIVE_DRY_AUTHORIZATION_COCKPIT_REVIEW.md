# R109 First-Live Dry Authorization Cockpit Review

## Phase

`R109`

## Branch

`r109-first-live-dry-authorization-cockpit-review`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R108 added a minimal operator approval cockpit that records intent only. R109 should review and harden that cockpit before any later phase considers dry authorization or execution-adjacent work.

R109 must remain non-executing unless a later phase and current user turn explicitly authorize execution behavior.

## Assigned Agents

- builder: inspect and make surgical hardening fixes only if required
- index: confirm R108 source-of-truth alignment and duplicate-risk boundaries
- qa: run focused endpoint, ledger, and UI safety tests
- security: verify no execution authority, no secrets, and no approval bypass

## Main Objective

Review, harden, and validate the R108 operator approval cockpit as a non-executing intent and diagnostic surface.

## Capability Scan

Inspect:

- `AGENTS.md`
- `AGENTS.builder.md`
- `AGENTS.index.md`
- `AGENTS.qa.md`
- `AGENTS.security.md`
- `codex_tasks/CODEX_RULES.md`
- `codex_tasks/agents/AGENT_WORKFLOW.md`
- `docs/hammer_radar/live_readiness/R108_FIRST_LIVE_OPERATOR_APPROVAL_COCKPIT.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/approval_api.py`
- `src/app/hammer_radar/operator/final_live_preflight.py`
- `src/app/hammer_radar/operator/tiny_live_armed_dry_run.py`
- `src/app/hammer_radar/operator/one_tiny_live_order_protocol.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `tests/hammer_radar/test_operator_approval_cockpit.py`
- existing approval, Telegram, readiness, and execution-boundary tests

## Reuse / Extend / Create Decision

- Existing capability reused: R102-R106 readiness chain, existing approval API, append-only ledger pattern
- Existing capability extended: R108 cockpit adapter and tests if hardening is needed
- New capability created: none expected
- Why new code is necessary: only if review finds a safety, UX, or audit gap
- Why this does not duplicate prior work: R109 should harden the R108 adapter instead of creating another cockpit or gate

## Duplicate Risk Report

- Similar existing modules: final preflight, dry run, protocol, activation gate, Telegram approval intent
- Similar existing endpoints: live arming, first-live, Telegram, and operator approval endpoints
- Similar existing CLI commands: `final-live-preflight`, `tiny-live-armed-dry-run`, `one-tiny-live-order-protocol`, `first-live-activation-gate`
- Similar existing scheduler tasks: none expected
- Similar existing docs: R101-R108 live-readiness docs
- Risk: HIGH
- Mitigation: keep R106 as authority and keep R108 as intent-only UI/ledger

## Files Expected

Likely inspect-only or surgical updates to:

- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/approval_api.py`
- `tests/hammer_radar/test_operator_approval_cockpit.py`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- optional R109 review doc under `docs/hammer_radar/live_readiness/`

## Tests Required

Validate:

- cockpit state remains non-executing
- UI contains intent-only and no-order labels
- expired windows reject approval
- missing candidate/hash data rejects approval
- counsel metadata records safely
- ledger remains append-only
- secrets are not exposed
- R106 remains source of authority
- no Binance order endpoint is called

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py src/app/hammer_radar/operator/approval_api.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_operator_approval_cockpit.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints unless explicitly authorized.
- Do not modify env flags.
- Do not expose secrets.
- Do not wire approval buttons to execution.
- Do not create execution authority.
- Preserve R106 as backend authority.
- Preserve paper/live separation.

## Do Not

- Do not run `sudo`.
- Do not attempt Git permission repair.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not restart services.
- Do not create a live order endpoint.

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
