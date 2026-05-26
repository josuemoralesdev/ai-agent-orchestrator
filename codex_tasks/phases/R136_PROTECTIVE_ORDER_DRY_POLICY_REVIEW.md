# R136 Protective Order Dry Policy Review

## Phase

`R136`

## Branch

`r136-protective-order-dry-policy-review`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R135 rehearses the live adapter boundary and keeps protective stop/take-profit readiness as a blocker. R136 must define the exact protective order dry policy before any future execution adapter implementation plan.

## Assigned Agents

- builder: implement protective dry policy review only
- index: verify reuse of existing protective status, risk contract, R132/R134/R135, and live-readiness gates
- qa: prove no Binance calls, no signed requests, no order payloads, and no real orders
- security: enforce credential, signing, network, and protective-order endpoint boundaries

## Main Objective

Define and audit the protective stop/take-profit dry policy required before future tiny-live adapter implementation, without creating exchange payloads or calling Binance.

## Capability Scan

Inspect:

- `src/app/hammer_radar/execution/binance_futures_connector.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `src/app/hammer_radar/operator/live_adapter_boundary_final_review.py`
- `src/app/hammer_radar/operator/first_tiny_live_order_payload_dry_authorization.py`
- `src/app/hammer_radar/operator/live_adapter_execution_rehearsal.py`
- `src/app/hammer_radar/operator/final_live_preflight.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/lane_controls.json`
- R132/R134/R135 docs and tests
- existing protective-order ledgers and CLI modes

## Required Safety Limits

- No Binance calls.
- No signed requests.
- No real orders.
- No test orders.
- No protective order endpoint calls.
- No executable exchange payloads.
- No env mutation.
- No lane config mutation.
- No global live flag changes.
- No live endpoint.
- No service start/restart.

## Required Output

R136 should report:

- selected lane key and risk contract hash
- protective stop requirement
- take-profit requirement
- stop/take-profit policy readiness
- required future protective payload fields without building the payload
- forbidden protective functions for R136
- exact blockers before protective dry preview can be considered
- exact blockers before live adapter implementation can be considered
- safety flags proving no order, no signed request, and no network

## Reuse / Extend / Create Decision

- Reuse existing protective status and risk contract builders.
- Reuse R132/R134/R135 blocker semantics.
- Extend inspect CLI with a review-only protective dry policy mode if needed.
- Do not call `protective_preview`, `submit_protective_test`, or signed protective request builders.
- Do not create real protective adapter behavior.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <changed_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <targeted_r136_tests>
```

Broaden to `tests/hammer_radar` if shared live-readiness or connector surfaces are changed.

## Do Not

- Do not place orders.
- Do not call Binance.
- Do not call connector `protective_preview`, `submit_protective_test`, `execute_live_order`, or signed request builders.
- Do not mutate env/config.
- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart services.

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
- Safety result:
- Blockers, if any:
- Exact manual commands needed, if any:
