# R110 First-Live Operator Path Review

## Phase

`R110`

## Branch

`r110-first-live-operator-path-review`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R110 is the final non-executing operator path review and readiness rehearsal after the R109 cockpit hardening. It verifies that the R108/R109 cockpit is understandable, correctly blocked, and still incapable of execution.

## Assigned Agents

- builder: review-only validation and small documentation/test refinements if needed
- index: confirm no duplicate approval or readiness authority was introduced
- qa: run focused cockpit and live-readiness validation
- security: verify no execution path, no secret exposure, and no Binance order calls

## Main Objective

Walk through the hardened first-live cockpit and prove the operator path, blocker hierarchy, sacred button state, and no-execution boundary are clear and correct.

## Scope

R110 must remain non-executing unless a later phase and current user turn explicitly authorize execution. This phase should not add execution authority.

Review:

- `GET /operator/approval-cockpit`
- `GET /operator/approval-cockpit/state`
- `POST /operator/approval-cockpit/intent`
- R102 final preflight status
- R104 dry-run status
- R105 protocol status
- R106 activation gate status
- R109 sacred button state
- blocker hierarchy
- operator path-to-press panel
- simultaneous signal tags
- countdown/window behavior

## Required Checks

- Walk through the cockpit UI.
- Validate every gate in the operator path.
- Verify the sacred button state and label.
- Verify blocked and expired states disable the button.
- Verify blocker priority and primary blocker summary.
- Verify operator comprehension copy says intent only.
- Verify no execution path exists.
- Verify no Binance order endpoint is called.
- Verify no env flags are modified.
- Verify no secrets are exposed.
- Verify paper/live separation remains intact.

## Safety Constraints

- Do not place orders.
- Do not enable live trading.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints.
- Do not modify env flags.
- Do not create a live order endpoint.
- Do not wire the cockpit to execution.
- Do not send Telegram messages.
- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart services.

## Validation Commands

```bash
git diff --check
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_operator_approval_cockpit.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Expected Outcome

R110 should produce a final readiness rehearsal report. The report should state whether the cockpit is understandable, whether every blocker is visible, whether the sacred button behaves correctly, and whether the system remains non-executing.
