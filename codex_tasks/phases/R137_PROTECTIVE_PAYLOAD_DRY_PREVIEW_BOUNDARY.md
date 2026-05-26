# R137 Protective Payload Dry Preview Boundary

## Phase

`R137`

## Branch

`r137-protective-payload-dry-preview-boundary`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R136 defines the non-executing protective stop-loss and take-profit policy boundary. R137 should define the next dry-preview boundary for protective payloads without producing executable Binance payloads, signed requests, or network calls.

## Assigned Agents

- builder: implement protective dry-preview boundary only if R136 readiness exists
- index: verify reuse of R136, R134, R135, R132, risk contract, and paper proof surfaces
- qa: prove no real orders, no Binance calls, no signed requests, and no submit-ready payloads
- security: enforce endpoint, signing, secret, and protective-order network boundaries

## Main Objective

Define a future abstract protective payload dry-preview review that can only run after R136 is ready and recorded, while proving the preview cannot be submitted to an exchange.

## Capability Scan

Inspect:

- `src/app/hammer_radar/operator/protective_order_dry_policy_review.py`
- `src/app/hammer_radar/operator/first_tiny_live_order_payload_dry_authorization.py`
- `src/app/hammer_radar/operator/live_adapter_execution_rehearsal.py`
- `src/app/hammer_radar/operator/live_adapter_boundary_final_review.py`
- `src/app/hammer_radar/execution/binance_futures_connector.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `src/app/hammer_radar/operator/lane_control.py`
- R132/R134/R135/R136 docs and tests
- existing protective ledgers and inspect CLI modes

## Required Safety Limits

- No real orders.
- No Binance calls.
- No Binance test-order calls.
- No protective order endpoint calls.
- No signed requests.
- No executable Binance payloads.
- No submit-ready protective payloads.
- No env mutation.
- No lane config mutation.
- No global live flag changes.
- No live endpoint.
- No service start/restart.

## Required Behavior

R137 may build only an abstract non-executable dry preview after R136 readiness is recorded. The preview must prove:

- R136 review is ready and hash-stable.
- Stop-loss and take-profit policy references exist.
- Any preview object is explicitly non-submit-ready.
- No endpoint, base URL, timestamp, `recvWindow`, signature, API key, secret, query string, or network target is present.
- Stop-loss and take-profit preview cannot be sent directly to Binance.
- Protective preview does not call `protective_preview`, `submit_protective_test`, signed request builders, or adapter send functions.

## Reuse / Extend / Create Decision

- Reuse R136 as the protective policy source of truth.
- Reuse R134/R135/R132 for non-executing adapter and payload boundaries.
- Do not duplicate risk contract or lane readiness logic.
- Create new code only if it is a distinct abstract preview boundary over the R136 packet.

## Tests Required

Add focused tests proving:

- blocked when R136 is missing, blocked, or not recorded
- abstract preview contains no secrets, endpoints, signed material, or executable exchange payload
- stop-loss preview is not submit-ready
- take-profit preview is not submit-ready
- no Binance/order/protective/network functions are called
- safety flags remain false
- ledger writes, if any, are append-only and confirmation-gated

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <changed_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <targeted_r137_tests>
```

Broaden to `tests/hammer_radar` if shared live-readiness or connector surfaces are modified.

## Do Not

- Do not place orders.
- Do not call Binance.
- Do not call connector `protective_preview`, `submit_protective_test`, `execute_live_order`, or signed request builders.
- Do not create executable protective payloads.
- Do not create signed request material.
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
