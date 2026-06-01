# R163 Funding Readonly Precheck And Balance Gate

## Phase

`R163`

## Branch

`r163-funding-readonly-precheck-and-balance-gate`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R162 keeps the 8m short risk-contract apply review blocked partly because funding is `UNKNOWN_NOT_CHECKED`. R163 should classify funding readiness through safe local/read-only surfaces without creating execution authority.

## Assigned Agents

- builder: implement read-only funding precheck only
- index: map existing Binance/read-only connector status surfaces before implementation
- qa: verify no order, signed request, secret, env, config, or live flag mutation
- security: enforce Binance private/trading boundary and secret handling

## Main Objective

Safely check local Binance read-only connector readiness and, only if an existing connector supports it safely, optionally perform a read-only balance check that reports funding status and remaining blockers.

## Capability Scan

Inspect before implementation:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/`
- `src/app/hammer_radar/operator/`
- `src/app/hammer_radar/execution/`
- existing Binance status/read-only connector modules
- existing inspect CLI commands
- tests around Binance status, live arming preflight, funding config, R160, R161, and R162
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- existing logs/ledgers for funding or preflight records

## Reuse / Extend / Create Decision

- Existing capability reused: existing Binance read-only/status connector if present
- Existing capability extended: inspect CLI funding/readiness surfaces
- New capability created: only a narrow read-only funding precheck adapter if no existing command already reports the needed R162 blocker state
- Why new code is necessary: R162 needs a funding status that is explicit and separate from execution authorization
- Why this does not duplicate prior work: it must wrap existing read-only status surfaces and produce only a blocker classification

## Duplicate Risk Report

- Similar existing modules: Binance status, live arming preflight, final live preflight, R160 dry-run packet
- Similar existing endpoints: operator readiness/status endpoints
- Similar existing CLI commands: Binance read-only/status and live preflight inspect commands if present
- Similar existing scheduler tasks: none expected
- Similar existing docs: R160, R161, R162, R102/R106 live readiness docs
- Risk: HIGH
- Mitigation: reuse existing connector/status code, do not add execution paths, and keep funding as a prerequisite signal only

## Files Expected

- `src/app/hammer_radar/operator/<r163_funding_precheck_module>.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/<r163_funding_precheck_tests>.py`
- `docs/hammer_radar/live_readiness/R163_FUNDING_READONLY_PRECHECK_AND_BALANCE_GATE.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`

## Tests Required

- read-only preview creates no orders
- no signed trading request material
- no secrets printed
- no env/config/global live flag mutation
- no live enable
- unavailable connector reports blocked/not checked
- optional read-only balance check is opt-in and non-executing
- CLI exists
- safety flags clean

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/<r163_funding_precheck_tests>.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

## Safety Constraints

- no orders
- no Binance order endpoint calls
- no Binance test-order endpoint calls
- no protective order endpoint calls
- no signed trading request
- no secrets printed
- no env mutation
- no config mutation
- no live enable
- no lane mode mutation
- no global live flag mutation

## Do Not

- Do not run `sudo`
- Do not commit
- Do not merge
- Do not tag
- Do not push
- Do not deploy
- Do not restart services
- Do not place or preview executable orders

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
