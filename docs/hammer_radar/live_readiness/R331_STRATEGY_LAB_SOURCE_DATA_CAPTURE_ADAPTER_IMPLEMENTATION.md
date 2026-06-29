# R331 Strategy Lab Source Data Capture Adapter Implementation

## Why R331 Exists

R328 emitted normalized Strategy Lab evidence rows. R329 consumed those rows and ranked the highest-value source-data gaps:

- `missing_exit_outcome_comparison`
- `missing_raw_anchor_timeseries`
- `missing_betrayal_source_chain_data`
- `missing_mae_mfe`
- `missing_regime_split_capture`
- 8m short capture gap
- 13m near-miss exit gap
- 88m durability capture gap

R331 implements deterministic, read-only/source-ledger-only capture adapters for those gaps. It prepares structured source-data capture rows from existing local Strategy Lab ledgers and marks unavailable inputs `SOURCE_DATA_CAPTURE_PENDING`, `SOURCE_DATA_CAPTURE_LAB_ONLY`, or `SOURCE_DATA_CAPTURE_WATCH_ONLY`. It does not invent outcomes, anchor values, MAE/MFE, regime splits, or betrayal source-chain mappings.

Output ledger:

```text
logs/hammer_radar_forward/strategy_lab_source_data_capture_adapter.ndjson
```

Event type:

```text
R331_STRATEGY_LAB_SOURCE_DATA_CAPTURE_ADAPTER_IMPLEMENTATION
```

## Source-Data Row Schema

Every normalized source-data row includes:

- `capture_adapter_id`
- `source_row_id`
- `lane_key`
- `timeframe`
- `side`
- `entry_mode`
- `source_gap_id`
- `capture_family`
- `capture_name`
- `capture_status`
- `source_inputs`
- `derived_capture_fields`
- `source_chain`
- `used_existing_data_only=true`
- `synthetic_performance_created=false`
- `live_permission=false`
- `tiny_live_eligible_now=false`
- `promotion_event_written=false`
- `risk_contract_write_required=false`
- `observed_expansion_written=false`
- `scheduler_required=false`
- `blockers`

## Capture Adapters

R331 implements seven capture adapters:

- `exit_variant_comparison`: fixed TP/SL, early exit, late exit, trailing stop, partial exit, and invalidation tightening outcomes. Missing exact outcome sources remain pending with `exit_outcome_source_missing`.
- `ma_wma_anchor_enrichment`: WMA200, MA200, close-vs-anchor, slope, and golden-pocket anchor confluence. Missing raw candle/MA inputs remain pending with `anchor_timeseries_source_missing`.
- `review_ready_enrichment`: recent stability, regime split, MAE/MFE, exit sensitivity, and anchor confluence for the 44m/55m review-ready lanes.
- `short_capture_improvement`: 8m short capture repair observations. It can surface existing evidence counts, but it cannot promote the lane.
- `near_miss_variant_capture`: 13m long/short timing, partial entry, exit variants, RSI/regime, anchor, and golden-pocket context.
- `betrayal_inverse_source_chain`: lab-only original/inverse identity, comparison, exact risk mapping, freshness, and stale-shadow audit rows.
- `watch_88m_durability`: watch-only durability, confirmation delay, HTF bias, exit variant, and anchor filter rows.

## Betrayal Lab-Only Rules

The betrayal/inverse packet always preserves:

- `lab_only=true`
- `standard_55_policy_applies=false`
- `source_chain_required=true`
- `exact_risk_mapping_required=true`
- `stale_shadow_outcomes_forbidden=true`
- `synthetic_performance_created=false`
- `live_permission=false`
- `tiny_live_eligible_now=false`

Missing betrayal data is not promoted into standard Strategy Lab comparison. It remains source-chain capture work for lab review only.

## Remaining Source-Data Gaps

R331 groups remaining gaps as:

- `exit_outcome_source_missing`
- `anchor_timeseries_source_missing`
- `mae_mfe_source_missing`
- `regime_split_source_missing`
- `betrayal_source_chain_source_missing`
- `watch_88m_durability_source_missing`

Rows with unavailable local inputs stay pending or lab/watch-only. R331 does not fake source data.

## R332/R330 Path

Recommended R332:

```text
Strategy Lab Captured Source Data Merge Into Adapter Rows
```

R332 should merge captured and pending R331 source-data rows back into the R328/R329 adapter comparison flow.

Recommended R330:

```text
Human-Reviewed Observed Expansion Promotion Gate
```

R330 can later alter observed expansion only after human review. R331 itself writes no promotion events, no risk contracts, and no observed expansion changes.

## Tiny Live Path

Tiny Live remains separately gated. The first Tiny Live lane remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

R331 does not arm, submit, create a final command, or change live permission.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable the kill switch, mutate arming state, submit, create a final command, change the first Tiny Live lane, write promotion events, write risk contracts, mutate observed expansion, mutate config, mutate env, mutate systemd, start schedulers, send Telegram, or send real Telegram.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-source-data-capture-adapter
bash scripts/hammer_print_r331_strategy_lab_source_data_capture_adapter.sh
```
