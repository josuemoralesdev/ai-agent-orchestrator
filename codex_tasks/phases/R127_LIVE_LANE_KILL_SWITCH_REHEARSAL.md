# R127 Live Lane Kill-Switch Rehearsal

## Phase

`R127`

## Branch

`r127-live-lane-kill-switch-rehearsal`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R126 creates the final non-executing first tiny-live lane execution gate. Before any later dry authorization or execution-adapter review, the live lane kill switch and rollback path must be rehearsed with no real orders and no Binance order endpoints.

## Main Objective

Rehearse the live lane kill-switch and rollback path for the tiny-live lane without creating order payloads, calling Binance order endpoints, enabling live execution, or mutating env files.

## Capability Scan

Inspect:

- R106 first-live activation gate
- R122 lane control
- R124 lane command interface
- R126 first tiny-live lane execution gate
- global kill-switch and live flag status surfaces
- emergency cancel and protective readiness docs
- `src/app/hammer_radar/operator/inspect.py`
- `configs/hammer_radar/lane_controls.json`
- existing lane-control and R126 tests

## Required Behavior

R127 should verify:

- lane stop conditions are explicit
- emergency disable path is visible
- lane mode rollback can be previewed and audited
- global kill switch semantics remain authoritative
- R126 becomes blocked when kill-switch or rollback conditions are unsafe
- paper/live separation remains intact

## Safety Constraints

- no real orders
- no Binance order endpoints
- no signed requests
- no executable order payloads
- no account or balance calls
- no env file mutation
- no live flag enablement
- no service restarts
- no `sudo`

## Expected Output

Add a non-executing rehearsal artifact or command that reports kill-switch rehearsal status, rollback commands for operator review, blockers, safety fields, and source surfaces used.

## Validation

Run focused compile and tests for any changed modules, then run the relevant Hammer Radar test subset.
