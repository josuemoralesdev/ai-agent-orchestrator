# R160 Fundless Short Dry-Run Packet And Operator Arming Checklist

## Phase

`R160`

## Branch

`r160-fundless-short-dry-run-packet-and-operator-arming-checklist`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R159 built the fundless readiness rehearsal shell for `BTCUSDT|8m|short|ladder_close_50_618`. R160 should turn that shell into a more detailed non-executable dry-run packet and operator arming checklist while preserving all no-live, no-payload, no-lane-change boundaries.

## Assigned Agents

- builder: implement the packet/checklist surface
- index: verify reuse and update phase indexes
- qa: validate preview/record and safety invariants
- security: enforce no live execution, no payloads, no Binance calls, no secrets

## Main Objective

Build a detailed fundless short dry-run packet and operator arming checklist for the BTCUSDT 8m short lane, using R159/R158/R156/R157 evidence and local read-only config only.

## Capability Scan

Inspect at minimum:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R159_FUNDLESS_8M_SHORT_TINY_LIVE_READINESS_REHEARSAL.md`
- `src/app/hammer_radar/operator/fundless_short_tiny_live_readiness_rehearsal.py`
- `src/app/hammer_radar/operator/short_evidence_recheck_packet.py`
- `src/app/hammer_radar/operator/short_strategy_packet.py`
- `src/app/hammer_radar/operator/short_paper_evidence_capture_loop.py`
- `src/app/hammer_radar/operator/lane_control.py`
- `configs/hammer_radar/lane_controls.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `tests/hammer_radar/test_fundless_short_tiny_live_readiness_rehearsal.py`
- existing inspect CLI commands
- existing ledgers under `logs/hammer_radar_forward/`

## Reuse / Extend / Create Decision

- Existing capability reused: R159 fundless rehearsal, R158 evidence recheck, R156 short strategy packet, R157 capture records, R122 lane controls.
- Existing capability extended: add a detailed non-executable packet/checklist surface over R159.
- New capability created: only the dry-run packet/checklist wrapper and optional append-only diagnostic ledger.
- Why new code is necessary: R159 identifies gates and blockers; R160 should define the later operator arming checklist in more detail without using execution code.
- Why this does not duplicate prior work: it must consume R159 instead of rebuilding the evidence and gate logic.

## Duplicate Risk Report

- Similar existing modules: R159 rehearsal, R158 evidence recheck, R156 short strategy packet, R134/R135 dry authorization and adapter boundary rehearsals.
- Similar existing endpoints: none required unless explicitly requested.
- Similar existing CLI commands: `fundless-short-tiny-live-readiness-rehearsal`, `short-evidence-recheck-packet`, `short-strategy-packet`.
- Similar existing scheduler tasks: none.
- Similar existing docs: R156, R157, R158, R159 live-readiness docs.
- Risk: HIGH.
- Mitigation: compose R159 and local read-only config; do not create execution logic, order payloads, or lane config mutation paths.

## Files Expected

- Add a focused operator module for R160 or extend R159 only if it remains clearly scoped.
- Wire one inspect CLI mode.
- Add focused tests.
- Add `docs/hammer_radar/live_readiness/R160_FUNDLESS_SHORT_DRY_RUN_PACKET_AND_OPERATOR_ARMING_CHECKLIST.md`.
- Update `docs/hammer_radar/live_readiness/PHASE_INDEX.md`.

## Tests Required

- preview writes no record
- wrong confirmation rejects record
- exact confirmation records packet/checklist only
- no executable payload is created
- no Binance/order/network/env/config/global mutation
- no lane mode apply commands emitted
- funding verification remains a future read-only/manual step
- short lane remains paper
- CLI exists

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <new_or_modified_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused_test_file>
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_fundless_short_tiny_live_readiness_rehearsal.py
```

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order, test-order, protective, or private trading endpoints.
- Do not create executable order or protective payloads.
- Do not sign requests.
- Do not mutate env files.
- Do not mutate global live flags.
- Do not mutate lane config.
- Do not set any short lane to `tiny_live`.
- Do not disable the kill switch.
- Do not expose secrets.

## Do Not

- Do not run `sudo`.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not restart services.

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
