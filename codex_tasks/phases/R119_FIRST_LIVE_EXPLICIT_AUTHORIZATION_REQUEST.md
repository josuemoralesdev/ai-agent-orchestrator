# R119 First-Live Explicit Authorization Request

## Phase

`R119`

## Branch

`r119-first-live-explicit-authorization-request`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R118 creates the final non-executing activation-gate review. R119 should request explicit first-live authorization only if R118 reports `READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION`, while preserving the boundary that no order is placed and no execution authority is created by default.

## Assigned Agents

- builder: implement only the authorization-request package, not execution
- index: preserve R106 authority and R118 request-readiness boundary
- qa: prove the request remains non-executing and blocked unless R118 is ready
- security: verify no Binance calls, no env edits, no secrets, and no request-to-execution wiring

## Main Objective

Create a non-executing explicit first-live authorization request surface that can be opened only after R118 says `READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION`.

## Capability Scan

Inspect:

- `docs/hammer_radar/live_readiness/R106_FIRST_LIVE_ACTIVATION_GATE.md`
- `docs/hammer_radar/live_readiness/R109_FIRST_LIVE_COCKPIT_SACRED_BUTTON_HARDENING.md`
- `docs/hammer_radar/live_readiness/R118_FIRST_LIVE_ACTIVATION_GATE_FINAL_REVIEW.md`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_operator_approval_cockpit.py`
- `src/app/hammer_radar/operator/first_live_activation_gate_final_review.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/`

## Reuse / Extend / Create Decision

- Existing capability reused: R118 final review, R106 activation gate, R109 sacred button state.
- Existing capability extended: inspect CLI only if a command is added.
- New capability created: authorization request record/report if needed.
- Why new code is necessary: R119 needs a clear human authorization request artifact after R118 readiness.
- Why this does not duplicate prior work: R119 asks for authorization; it does not re-evaluate the whole gate or execute.

## Duplicate Risk Report

- Similar existing modules: R106 activation gate, R109 cockpit, R118 final review.
- Similar existing endpoints: R109 cockpit intent endpoint.
- Similar existing CLI commands: `first-live-activation-gate`, `first-live-activation-final-review`.
- Similar existing scheduler tasks: none expected.
- Similar existing docs: R106/R109/R118 live readiness docs.
- Risk: HIGH.
- Mitigation: consume R118 as the source readiness signal, keep R106 as authority, and do not create execution wiring.

## Required Behavior

R119 should:

- refuse to request authorization unless the latest or fresh R118 result is `READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION`
- include the exact confirmation phrase template from R118/R105
- state that human authorization is a request artifact only
- state that no execution occurs in R119
- keep all safety fields false
- require a later explicit execution phase before any order placement can be considered

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints.
- Do not modify env flags.
- Do not expose secrets.
- Do not create a live order endpoint.
- Do not wire authorization to execution.
- Preserve R106 as activation authority.
- Preserve R109 as intent-only.

## Tests Required

- blocked when R118 is not `READY_TO_REQUEST_FIRST_LIVE_AUTHORIZATION`
- request artifact includes exact confirmation phrase template
- request returns `live_ready=false`
- request returns execution enablement false
- request never places orders
- request never calls Binance
- request never exposes secrets
- request ledger includes safety fields

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_first_live_explicit_authorization_request.py
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
- Do not place a live order.

## Final Human Boundary

R119 may only request explicit authorization. Even a recorded authorization request must not execute. A later execution phase must be separately scoped, separately reviewed, and explicitly authorized in the current turn before any live order path is touched.
