# R309 Capability Reuse Report

## Phase Classification

Primary classification: `WIRING / INTEGRATION`

Secondary classification: `DIAGNOSTIC / AUDIT`

Duplicate risk level: `MEDIUM`

Reason: R309 intentionally resembles existing risk-contract write gates. The selected implementation reuses the R308 preview row builder and existing validation helper while adding a distinct human-reviewed multi-row append boundary.

## Capability Scan

Existing docs checked:

- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R308_EXPANSION_RISK_CONTRACT_WRITE_GATE_PREVIEW.md`

Existing configs checked:

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`

Existing modules checked:

- `src/app/hammer_radar/operator/expansion_risk_contract_write_gate_preview.py`
- `src/app/hammer_radar/operator/expansion_risk_contract_preview_repair.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract_config_write_gate.py`
- `src/app/hammer_radar/operator/tiny_live_leverage_notional_risk_contract_write_gate.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py`
- `src/app/hammer_radar/operator/inspect.py`

Existing tests checked:

- `tests/hammer_radar/test_expansion_risk_contract_write_gate_preview.py`
- `tests/hammer_radar/test_tiny_live_risk_contract_config_write_gate.py`
- `tests/hammer_radar/test_eligible_lane_expansion_dry_run_preview.py`

Existing endpoints checked:

- `tiny-live/final-console` was identified as the live-safety smoke endpoint required after validation.

Existing CLI commands checked:

- `expansion-risk-contract-write-gate-preview`
- `expansion-risk-contract-preview-repair`
- `eligible-lane-expansion-dry-run-preview`
- `tiny-live-risk-contract-config-write-gate`
- `tiny-live-leverage-notional-risk-contract-write-gate`

Existing scheduler tasks checked:

- No scheduler task is reused in R309. R309 remains a local operator gate and points R310 toward dry-run observation scheduling only after manual apply and verification.

Existing logs/ledgers checked:

- `logs/hammer_radar_forward/expansion_risk_contract_write_gate_preview.ndjson`
- `logs/hammer_radar_forward/expansion_risk_contract_preview_repair.ndjson`
- `logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_leverage_notional_risk_contract_write_gate.ndjson`

## Existing Write Gate Patterns

`tiny_live_risk_contract_config_write_gate.py` and `tiny_live_leverage_notional_risk_contract_write_gate.py` establish the local write-gate pattern:

- default read/preview behavior
- exact confirmation phrase for writes
- validation before write
- local config-only mutation
- no Binance/network/order/env/lane-control side effects
- temp-file write followed by replace
- explicit safety fields in output

R309 follows that pattern but writes multiple missing expansion rows rather than updating a single lane.

## Existing Config Schema

`configs/hammer_radar/tiny_live_risk_contracts.json` uses:

- top-level `funding_config`
- top-level `risk_contracts` list

R309 preserves this shape and appends missing rows to `risk_contracts`.

The current arming state is stored separately in `configs/hammer_radar/autonomous_arming_state.json`. R309 does not write that file.

## Existing Backup / Write / Atomic Helpers

The prior write gates use `NamedTemporaryFile` in the target directory and `replace()` for atomic config replacement.

R309 reuses that local atomic-write pattern and adds a timestamped backup beside the target config before any confirmed write.

## Duplicate Risks

Similar existing modules:

- `tiny_live_risk_contract_config_write_gate.py`
- `tiny_live_leverage_notional_risk_contract_write_gate.py`
- `expansion_risk_contract_write_gate_preview.py`

Similar existing endpoints or inspect routes:

- `tiny-live-risk-contract-config-write-gate`
- `tiny-live-leverage-notional-risk-contract-write-gate`
- `expansion-risk-contract-write-gate-preview`

Similar CLI commands:

- module CLI for R308 write-gate preview
- inspect route for R308 write-gate preview
- operator script for R308 write-gate preview

Similar scheduler tasks:

- none directly; R309 is not a scheduler.

Similar docs:

- `docs/hammer_radar/live_readiness/R308_EXPANSION_RISK_CONTRACT_WRITE_GATE_PREVIEW.md`

Risk: `MEDIUM`, because a careless implementation could duplicate R230/R244 semantics or accidentally make preview confirmation executable through R308.

Mitigation:

- R309 uses a new module boundary with a new event type and ledger.
- R309 reuses R308's lane spec and proposed-row builder.
- R309 inspect route is preview-only.
- R309 applies only with `--apply` plus exact phrase.
- R309 appends missing rows only and skips existing exact keys.
- R309 keeps live/order/Binance/env/arming safety fields false.

## Selected Implementation Path

Selected path:

- create `expansion_risk_contract_human_reviewed_write_gate.py`
- reuse R308 proposed rows through `build_r308_lane_specs()` and `build_proposed_contract_row()`
- reuse `build_tiny_live_risk_contract_validation_summary()` for row validation
- preserve config shape and append missing exact rows only
- add a dedicated inspect route that calls preview mode only
- add a preview-only operator script
- add targeted tests covering temp-path apply behavior

## Reuse / Extend / Create Decision

Existing capability reused:

- R308 proposed lane set and row builder
- tiny-live risk contract validation summary
- existing inspect command pattern
- prior write-gate exact confirmation pattern
- prior atomic write pattern

Existing capability extended:

- `inspect.py` gains `expansion-risk-contract-human-reviewed-write-gate`

New capability created:

- R309 multi-row human-reviewed append gate
- R309 ledger
- R309 operator script
- R309 docs and tests

Why new code was necessary:

- R308 is intentionally preview-only and has no active confirmation or apply function.
- R230/R244 write gates target different single-lane risk-contract workflows.
- R309 needs a bounded multi-row append behavior for the exact R308-reviewed lane set.

Why this is not duplicating prior work:

- It does not rebuild R308 proposal logic.
- It does not introduce a new contract schema.
- It does not replace R230/R244 single-lane gates.
- It only adds the missing human-reviewed append step for the R308 expansion rows.

## Why R309 Still Does Not Enable Live Or Arm Lanes

R309 only writes local risk-contract rows after exact manual confirmation. Each new row keeps:

- `live_execution_enabled=false`
- `allow_live_orders=false`

R309 never writes:

- `configs/hammer_radar/autonomous_arming_state.json`
- env files
- live flags
- lane controls
- order payloads

R309 never calls:

- Binance order endpoint
- Binance test order endpoint
- leverage change endpoint
- margin change endpoint

R309 output keeps:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `submit_allowed=false`
- `final_command_available=false`
- `real_order_forbidden=true`
- `global_kill_switch=true`
- `paper_live_separation_intact=true`
