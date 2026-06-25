# R308 Capability Reuse Report

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION
- Duplicate risk level: MEDIUM
- Reason: R308 resembles existing risk-contract preview and write-gate modules, but its boundary is distinct: it prepares multi-lane expansion write-gate review packets without activating any config write.

## Capability Scan

Existing docs checked:

- `README.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R307_EXPANSION_RISK_CONTRACT_PREVIEW_REPAIR.md`
- `docs/hammer_radar/live_readiness/PHASE_INDEX.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`

Existing modules checked:

- `src/app/hammer_radar/operator/expansion_risk_contract_preview_repair.py`
- `src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract_config_write_gate.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract_preview.py`
- `src/app/hammer_radar/operator/inspect.py`

Existing tests checked:

- `tests/hammer_radar/test_expansion_risk_contract_preview_repair.py`
- `tests/hammer_radar/test_eligible_lane_expansion_dry_run_preview.py`
- `tests/hammer_radar/test_tiny_live_risk_contract_config_write_gate.py`
- `tests/hammer_radar/test_tiny_live_risk_contract_preview.py`
- `tests/hammer_radar/test_strategy_lab_variant_test_pack.py`
- `tests/hammer_radar/test_strategy_lab_preview.py`
- `tests/hammer_radar/test_paper_refresh_scheduler.py`

Existing endpoints checked:

- `src/app/hammer_radar/operator/inspect.py` routes for `eligible-lane-expansion-dry-run-preview`, `expansion-risk-contract-preview-repair`, `tiny-live-risk-contract-preview`, and `tiny-live-risk-contract-config-write-gate`.

Existing CLI commands checked:

- `python -m src.app.hammer_radar.operator.expansion_risk_contract_preview_repair`
- `python -m src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview`
- `python -m src.app.hammer_radar.operator.inspect expansion-risk-contract-preview-repair`
- `python -m src.app.hammer_radar.operator.inspect tiny-live-risk-contract-config-write-gate`

Existing scheduler tasks checked:

- `src/app/hammer_radar/operator/paper_refresh_scheduler.py`
- `src/app/hammer_radar/operator/lane_autonomy_scheduler.py`
- `src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py`
- R306/R307 do not add expansion scheduler mutation.

Existing logs/ledgers/configs checked:

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- `logs/hammer_radar_forward/eligible_lane_expansion_dry_run_preview.ndjson`
- `logs/hammer_radar_forward/expansion_risk_contract_preview_repair.ndjson`
- `logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson`

## Current Risk Contract Schemas

The repo currently uses:

- legacy R84.1 candidate rows keyed by `candidate_id`
- official-lane rows keyed by `official_lane_key`
- derived lookup keys built from `symbol|timeframe|direction|entry_mode`
- R267 explicit notional mode: `tiny_live_contract_mode=explicit_notional_cap_with_leverage`
- accepted R267 envelope: `max_position_notional_usdt=80`, `leverage=10`, `margin_budget_usdt=8`, `max_loss_usdt<=4.44`

## Existing Write-Gate Modules

Relevant write-gate modules already exist for single-lane or later tiny-live flows:

- `tiny_live_risk_contract_config_write_gate.py`
- `tiny_live_leverage_notional_risk_contract_write_gate.py`
- `tiny_live_lane_arm_write_gate.py`
- `tiny_live_order_preflight_write_gate.py`
- `tiny_live_order_payload_write_gate.py`
- `tiny_live_executable_payload_write_gate.py`
- `tiny_live_signed_request_write_gate.py`
- `tiny_live_actual_submit_gate.py`

R308 does not reuse their write functions because this phase must not write config. It reuses their preview/write-gate vocabulary and the shared validation helper.

## Proposed R308 Contract Schema

Each proposed R308 row contains:

- `official_lane_key`
- `contract_version=r308_expansion_risk_contract_preview_v1`
- `created_by_phase=R308_EXPANSION_RISK_CONTRACT_WRITE_GATE_PREVIEW`
- `symbol`
- `timeframe`
- `direction`
- `entry_mode`
- `tiny_live_contract_mode=explicit_notional_cap_with_leverage`
- `margin_mode=isolated`
- `leverage=10`
- `max_position_notional_usdt=80`
- `max_notional_usdt=80`
- `margin_budget_usdt=8`
- `max_margin_usdt=8`
- `tiny_live_margin_usdt=8`
- `max_loss_usdt`, derived only from `funding_config.max_loss_usdt` when safe
- `max_trades_per_day=1`
- `daily_loss_stop_usdt=5`
- `protective_orders_required=true`
- `protective_stop_required=true`
- `take_profit_required=true`
- `live_execution_enabled=false`
- `allow_live_orders=false`
- `live_authorized=false`
- `approval_status=R308_PREVIEW_ONLY_NOT_WRITTEN`

## Reuse / Extend / Create Decision

- Existing capability reused: R307 lane list and lane-key normalization, shared tiny-live risk-contract validation, inspect command style, NDJSON ledger style, operator script style.
- Existing capability extended: `inspect.py` gains the R308 route.
- New capability created: `expansion_risk_contract_write_gate_preview.py`.
- Why new code was necessary: R307 produces missing templates; R308 must produce complete proposed rows, validation previews, diff previews, max-loss derivation, and future operator review language.
- Why this is not duplicating prior work: existing write gates can mutate config with explicit confirmation, while R308 intentionally has no active write path.

## Duplicate Risk Report

- Similar existing modules: R307 preview repair, R229 risk-contract preview, R230 risk-contract config write gate.
- Similar existing endpoints: `expansion-risk-contract-preview-repair`, `tiny-live-risk-contract-preview`, `tiny-live-risk-contract-config-write-gate`.
- Similar existing CLI commands: the R307 and R230 module CLIs.
- Similar existing scheduler tasks: none that perform this preview packet.
- Similar existing docs: R306/R307 and R229/R230 live-readiness docs.
- Risk: accidentally creating a second write gate that can mutate config.
- Mitigation: R308 has no write confirmation argument, no config write function, no active phrase, and top-level/row safety fields force `config_written=false` and `risk_contract_config_mutated=false`.

## Why R308 Does Not Write Config

R308 is a preview-only human review packet. It writes only its own NDJSON preview ledger when requested by default. It does not write `configs/hammer_radar/tiny_live_risk_contracts.json`, does not write `configs/hammer_radar/autonomous_arming_state.json`, does not mutate env, and does not expose an executable confirmation phrase.
