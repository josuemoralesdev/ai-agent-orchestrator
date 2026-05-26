# R140 Operator Executes Safe Clearing Pack

## Phase

`R140`

## Branch

`r140-operator-executes-safe-clearing-pack`

## Phase Classification

- Primary classification: `DIAGNOSTIC / AUDIT`
- Secondary classification(s): `WIRING / INTEGRATION`, `EXTENSION OF EXISTING CAPABILITY`, `DUPLICATE RISK`
- Duplicate risk level: `HIGH`

## Reason

R139 creates the safe live-ready blocker clearing operator pack. R140 should assist the operator in executing only the safe portions of that pack and then produce a before/after comparison against R138/R139 state.

## Assigned Agents

- builder: implement the safe clearing assistant and CLI/reporting
- index: verify R140 reuses R139/R138/R138.5 and existing evidence commands
- qa: validate before/after comparison, no unsafe command execution, and ledger behavior
- security: enforce no live orders, no Binance calls, no env mutation, no live flag changes

## Main Objective

Assist the operator in executing safe R139 clearing stages only, then report what changed and what remains blocked.

## Scope

R140 may:

- run read-only rechecks from R139 stages
- preview safe commands
- record autonomous paper proof using the existing R129 confirmation phrase when explicitly provided
- produce before/after R138/R139 comparison
- write an append-only R140 assisted-clearing ledger if the exact R140 confirmation phrase is provided

R140 must not:

- place real orders
- call Binance order, test-order, account, or protective endpoints
- create executable order payloads
- create executable protective payloads
- sign requests
- mutate env files
- enable live flags
- disable the global kill switch
- mutate lane config without a separate explicit lane-mode apply phase
- treat R139 pack recording as command execution authorization

## Required Behavior

- Default mode is preview only.
- Safe read-only rechecks can run locally.
- R129 paper proof recording may run only through existing R129 logic and exact R129 phrase.
- Lane mode apply remains explicitly separated and confirmed outside R140 default flow.
- The output must include before/after R138 blocker counts, stage completion evidence, unchanged safety flags, and remaining blockers.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/operator_executes_safe_clearing_pack.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_operator_executes_safe_clearing_pack.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- no real orders
- no Binance calls
- no payload creation
- no signed requests
- no env/config mutation by default
- no live flag changes
- no kill-switch disablement
- paper/live separation stays intact
