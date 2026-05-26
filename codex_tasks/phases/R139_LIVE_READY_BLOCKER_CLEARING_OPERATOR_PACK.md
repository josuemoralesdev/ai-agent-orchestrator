# R139 Live-Ready Blocker Clearing Operator Pack

## Phase

`R139`

## Branch

`r139-live-ready-blocker-clearing-operator-pack`

## Phase Classification

- Primary classification: `DIAGNOSTIC / AUDIT`
- Secondary classification(s): `WIRING / INTEGRATION`, `EXTENSION OF EXISTING CAPABILITY`, `DUPLICATE RISK`
- Duplicate risk level: `HIGH`

## Reason

R138 ranks the remaining blockers between the autonomous lane system and first tiny-live autonomous execution. R139 should convert that ranked burn-down into an operator clearing pack that walks the exact blocker order with safe commands, evidence templates, stop conditions, and recheck points.

## Assigned Agents

- builder: implement the R139 pack and CLI wiring
- index: verify no duplicate clearing surface is created
- qa: validate command safety, ledger behavior, and no execution side effects
- security: verify no Binance calls, payload creation, signing, env mutation, or live flag changes

## Main Objective

Build an operator pack that clears or records evidence for R138 blockers in exact order while preserving all live-trading safety boundaries.

## Capability Scan

Inspect:

- `AGENTS.md`
- `AGENTS.builder.md`
- `AGENTS.index.md`
- `AGENTS.qa.md`
- `AGENTS.security.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R138_AUTONOMOUS_LANE_LIVE_READY_BURN_DOWN.md`
- `src/app/hammer_radar/operator/autonomous_lane_live_ready_burn_down.py`
- R122-R138 operator modules
- `src/app/hammer_radar/operator/inspect.py`
- `configs/hammer_radar/lane_controls.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `tests/hammer_radar/test_autonomous_lane_live_ready_burn_down.py`
- existing R110-R120 clearing/evidence runbook patterns

## Reuse / Extend / Create Decision

- Existing capability reused: R138 burn-down report, R124 lane command preview, R129 paper evidence, R130 authorization, R126 gate, R131 rehearsal, R132 boundary, R136/R137 protective reviews, R102/R106 preflights.
- Existing capability extended: inspect CLI and docs only if needed.
- New capability created: one R139 operator clearing pack module only if no existing clearing pack can represent R138 blocker order.
- Why new code is necessary: R138 is a diagnostic inventory; R139 should sequence clearing actions without changing readiness authority.
- Why this does not duplicate prior work: R139 must consume R138 output rather than recalculate independent live readiness.

## Safety Constraints

- No real orders.
- No Binance calls.
- No Binance test-order calls.
- No protective order endpoint calls.
- No executable order payloads.
- No executable protective payloads.
- No signed requests or signed request material.
- No secret printing.
- No env mutation.
- No lane config mutation unless a future explicit R139 subtask authorizes a specific R124 apply command and confirmation phrase.
- No global live flag changes.
- No live execution enabling.
- No R106/global gate weakening.
- No live adapter behavior.

## Allowed Work

- May include evidence recording commands.
- May include lane mode preview commands.
- May include lane mode application commands only as withheld future-apply commands, clearly marked not run by R139 unless separately authorized.
- May include R138/R126/R130/R131/R132/R136/R137/R102/R106 recheck commands.
- May write an append-only R139 clearing-pack ledger after exact confirmation.

## Expected Files

- `src/app/hammer_radar/operator/live_ready_blocker_clearing_operator_pack.py`
- `tests/hammer_radar/test_live_ready_blocker_clearing_operator_pack.py`
- `docs/hammer_radar/live_readiness/R139_LIVE_READY_BLOCKER_CLEARING_OPERATOR_PACK.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `src/app/hammer_radar/operator/inspect.py`

## Tests Required

- R139 consumes R138 ranked blockers.
- R139 preserves R138 blocker order.
- R139 command pack contains no live execution, Binance endpoint, env mutation, signed request, or payload creation commands.
- Evidence recording commands require exact phrases.
- Lane mode apply command is withheld or explicitly future-only by default.
- Preview writes no ledger.
- Wrong confirmation rejects recording.
- Exact confirmation records clearing pack only.
- Ledger append-only.
- Safety flags remain false and `paper_live_separation_intact=true`.
- No connector payload/signing/network functions are called.
- CLI mode exists and returns compact status.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/live_ready_blocker_clearing_operator_pack.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_live_ready_blocker_clearing_operator_pack.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

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
