# R329 Strategy Lab Adapter Output Batch Execution Packet

## Why R329 Exists

R328 implemented seven Strategy Lab evidence adapters and emitted normalized evidence rows. R329 consumes those rows and produces a deterministic, read-only comparison packet for adapter usefulness, source-data gaps, capture priorities, and human review inputs for later phases.

R329 does not promote candidates, write promotion events, write risk contracts, alter observed expansion, change Tiny Live, start schedulers, send Telegram, or execute trades.

## What R328 Produced

The current R328 ledger reports:

- 7 implemented adapters
- 154 normalized evidence rows
- 20 ready rows
- 124 rows needing source data
- 5 lab-only rows
- 5 watch-only rows
- 0 live permission
- 0 promotion writes
- 0 risk-contract writes
- 0 scheduler starts

Input ledger:

```text
logs/hammer_radar_forward/strategy_lab_evidence_adapter_pack.ndjson
```

R329 output ledger:

```text
logs/hammer_radar_forward/strategy_lab_adapter_output_batch_execution_packet.ndjson
```

Event type:

```text
R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET
```

## Ranking Logic

R329 uses deterministic, explainable scoring only. It does not invent win rates, sample counts, or performance metrics.

Usefulness score considers:

- ready row count
- candidate lane count
- near-miss candidate coverage
- review-ready candidate coverage
- 8m short near-threshold candidate coverage
- observed expansion review support
- lab-only and watch-only demotion

Source-data gap score considers:

- rows needing source data
- high-value candidate blockers
- exit, anchor, MAE/MFE, and betrayal source-chain gaps

## Adapter Usefulness Ranking

Expected high-priority adapters:

- `capture_8m_short`: 8m short is near threshold and has ready rows plus one missing exit/capture row.
- `review_ready_enrichment`: affects 44m/55m review-ready lanes and observed expansion review.
- `near_miss_13m`: 13m has many samples but weak win rate and needs repair dimensions.

`betrayal_inverse_lab` is excluded from the standard usefulness ranking because it remains lab-only.

## Source-Data Gap Ranking

Expected high source-data gap priorities:

- `exits`: exit outcome comparison has many missing rows.
- `ma_wma_anchor`: anchor confluence has many missing rows.
- `betrayal_inverse_lab`: source-chain data is required but lab-only.
- `review_ready_enrichment`: MAE/MFE and enrichment fields matter before observed expansion review.

## Capture Priorities

R329 recommends these next capture adapters:

- `short_capture_improvement_adapter`
- `exit_variant_comparison_adapter`
- `ma_wma_anchor_enrichment_adapter`
- `review_ready_enrichment_adapter`
- `near_miss_variant_capture_adapter`
- `betrayal_inverse_source_chain_adapter` lab-only
- `watch_88m_durability_adapter`

## Observed Expansion Review Inputs

R329 emits non-live review inputs only:

- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_22_44_22`
- `BTCUSDT|55m|long|ladder_close_50_618`
- `BTCUSDT|55m|long|market_close`

These are observed expansion review only, require human review, grant no Tiny Live change, expose no final command, and provide no live permission.

## Betrayal/Inverse Lab-Only Handling

Betrayal/inverse remains:

- `lab_only=true`
- `standard_55_policy_applies=false`
- `live_permission=false`
- `tiny_live_eligible_now=false`
- `source_chain_required=true`
- `exact_risk_mapping_required=true`
- `stale_shadow_outcomes_forbidden=true`
- `excluded_from_standard_ranking=true`
- `recommended_next_action=CAPTURE_LAB_ONLY_SOURCE_CHAIN_DATA`

## R330/R331 Path

Recommended R330:

```text
Human-Reviewed Observed Expansion Promotion Gate
```

R330 can alter observed expansion only after human review of R329. It must still not authorize live execution.

Recommended R331:

```text
Strategy Lab Source Data Capture Adapter Implementation
```

R331 can implement source-data capture for exits, anchors, MAE/MFE, and betrayal source chain.

## Tiny Live Path

Tiny Live remains separately gated. The first Tiny Live lane remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

R329 does not arm, submit, create a final command, or change live permission.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable the kill switch, mutate arming state, submit, create a final command, change the first Tiny Live lane, write promotion events, write risk contracts, mutate observed expansion, mutate config, mutate env, mutate systemd, start schedulers, send Telegram, or send real Telegram.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-adapter-output-batch-execution-packet
bash scripts/hammer_print_r329_strategy_lab_adapter_output_batch_execution_packet.sh
```
