# R138 Autonomous Lane Live-Ready Burn-Down

## Phase

`R138`

## Branch

`r138-autonomous-lane-live-ready-burn-down`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R137 defines the protective payload dry preview boundary but does not clear live-readiness blockers. R138 should rank the remaining blockers in exact execution order so the autonomous lane can be made live-ready without creating order payloads, signed requests, Binance calls, or real orders.

## Assigned Agents

- builder: implement only the burn-down diagnostic
- index: verify reuse of R122-R137 readiness surfaces and avoid duplicate gates
- qa: prove no live order, no Binance call, no signed request, and no env/config mutation
- security: enforce live-trading safety and secret boundaries

## Main Objective

Produce an autonomous lane live-ready burn-down that ranks remaining blockers in exact clearing order:

1. paper proof
2. tiny_live lane mode
3. authorization
4. protective readiness
5. credential presence
6. global gate
7. adapter readiness
8. final confirmation

## Capability Scan

Inspect:

- R122-R137 docs, modules, tests, CLI modes, ledgers, and configs
- `src/app/hammer_radar/operator/inspect.py`
- lane controls and tiny-live risk contracts
- R125/R129 paper proof ledgers
- R126/R130/R132/R134/R135/R136/R137 readiness records
- final live preflight and first live activation gate surfaces

## Safety Constraints

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

## Files Expected

Define exact files during R138 implementation after the capability scan. Prefer extending existing diagnostic/burn-down patterns over creating a duplicate readiness engine.

## Tests Required

Add focused tests proving:

- burn-down order is deterministic
- blockers are ranked in the requested order
- records, if any, are confirmation-gated and append-only
- no order payload, signed request, network call, Binance call, env mutation, or config mutation occurs

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <changed_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <targeted_r138_tests>
```

## Do Not

- Do not place orders.
- Do not call Binance.
- Do not call connector payload, signing, submit, or execution helpers.
- Do not create executable payloads.
- Do not mutate env/config.
- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart services.
