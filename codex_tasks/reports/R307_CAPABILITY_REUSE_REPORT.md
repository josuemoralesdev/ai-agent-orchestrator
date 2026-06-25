# R307 Capability Reuse Report

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION
- Duplicate risk level: MEDIUM
- Reason: R307 extends R306's existing risk-contract preview path and reuses the R265/R270B validation semantics instead of creating a write gate.

## Capability Scan Summary

Checked:

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py`
- `src/app/hammer_radar/operator/tiny_live_strategy_lane_selection.py`
- `src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py`
- `src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py`
- `src/app/hammer_radar/operator/tiny_live_final_authorization_gate.py`
- `src/app/hammer_radar/operator/tiny_live_final_console.py`
- `src/app/hammer_radar/operator/inspect.py`
- `docs/hammer_radar/live_readiness/R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW.md`
- `tests/hammer_radar/test_eligible_lane_expansion_dry_run_preview.py`
- `tests/hammer_radar/test_tiny_live_risk_contract*.py`
- `tests/hammer_radar/test_tiny_live_strategy_lane_selection.py`

## Current Risk Contract Config Structure

`configs/hammer_radar/tiny_live_risk_contracts.json` is a JSON object with:

- `funding_config`: local non-secret funding envelope, including `funding_config_present`, `funding_check_mode`, `max_loss_usdt`, and `max_margin_usdt`.
- `risk_contracts`: list of contract rows.

Current lane-key representations in the file:

- Older R84.1 row: `candidate_id=normal|BTCUSDT|13m|long|ladder_close_50_618`.
- Later Tiny Live row: `official_lane_key=BTCUSDT|8m|short|ladder_close_50_618`, plus explicit `symbol`, `timeframe`, `direction`, and `entry_mode`.

No secret values are present in this config. The active `autonomous_arming_state.json` lane is:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

That active lane is represented in arming state, not as an exact row in `tiny_live_risk_contracts.json`.

## How Exact Lane Lookup Worked Before R307

R306 called `build_exact_lane_risk_contract_status()` from `tiny_live_strategy_lane_selection.py`.

That path used `load_tiny_live_risk_contract_for_lane()` from `tiny_live_risk_contract_validation.py`, which searches each risk-contract row by:

- `official_lane_key`
- derived `symbol|timeframe|direction|entry_mode`

When no row matched, R306 passed an empty contract through the validation summary. That produced broad blockers such as:

- `risk_contract_config_missing`
- `risk_contract_symbol_not_BTCUSDT`
- `risk_contract_max_loss_missing`
- `risk_contract_margin_budget_missing`
- `risk_contract_leverage_missing`
- `risk_contract_notional_cap_missing`

## Why R306 Produced `exact_contract_found=false`

The current config contains exact rows for:

- `BTCUSDT|13m|long|ladder_close_50_618` through the older `candidate_id` row
- `BTCUSDT|8m|short|ladder_close_50_618` through `official_lane_key`

R306 inspected:

- `BTCUSDT|44m|long|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|55m|long|ladder_close_50_618`
- secondary 44m/55m/88m lanes

Those lane keys do not currently have exact risk-contract rows in `tiny_live_risk_contracts.json`, so exact lookup correctly fails in the current repo state. The repair separates true missing-contract status from invalid matched-contract validation.

## Selected Read-Only Repair Path

R307 adds `src/app/hammer_radar/operator/expansion_risk_contract_preview_repair.py`.

The resolver:

- normalizes `symbol|timeframe|direction|entry_mode`
- lists every lookup attempt
- records matched contract key and schema/version when found
- validates only matched contracts
- reports missing contracts with a preview template
- leaves `risk_contract_config_mutated=false` and `config_written=false`

R306 now consumes this resolver for `exact_risk_contract_preview`, so R306 output can distinguish missing exact rows from invalid matched rows.

## Duplicate Risks

Similar existing modules:

- `tiny_live_risk_contract_validation.py`
- `tiny_live_strategy_lane_selection.py`
- `tiny_live_risk_contract_preview.py`
- `tiny_live_risk_contract_config_write_gate.py`

Mitigation:

- R307 reuses the existing validation summary for matched rows.
- R307 does not write config and does not duplicate write-gate behavior.
- R307 keeps preview-template output separate from any config mutation path.

## Why This Phase Is Not A Write Gate

R307 has no confirmation phrase, no apply flag, and no config-write function. It emits operator-safe templates only:

- `safe_preview_template_status=PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN`
- `future_write_gate_required=true`
- `risk_contract_config_mutated=false`
- `config_written=false`

Any future write must be a separate human-reviewed gate phase.
