# R332 Strategy Lab Captured Source Data Merge Into Adapter Rows

## Why R332 Exists

R328 emitted normalized Strategy Lab evidence adapter rows. R329 ranked adapter usefulness and source-data gaps. R331 emitted normalized source-data capture rows:

- 164 normalized source-data rows
- 18 capture-ready rows
- 135 pending rows
- 6 lab-only rows
- 5 watch-only rows
- `synthetic_performance_created_count=0`
- `live_permission_count=0`
- `promotion_event_written_count=0`
- `risk_contract_write_required_count=0`
- `observed_expansion_written_count=0`
- `scheduler_required_count=0`

R332 merges R331 source-data status back into the R328/R329 adapter flow so downstream review can inspect one coherent evidence state.

Output ledger:

```text
logs/hammer_radar_forward/strategy_lab_captured_source_data_merge.ndjson
```

Event type:

```text
R332_STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_INTO_ADAPTER_ROWS
```

## Merge Row Schema

Every merged row includes:

- `merge_row_id`
- `adapter_row_id`
- `source_row_id`
- `adapter_id`
- `capture_adapter_id`
- `lane_key`
- `timeframe`
- `side`
- `entry_mode`
- `variant_family`
- `variant_name`
- `evidence_status_from_adapter`
- `capture_status_from_source`
- `merged_status`
- `source_gap_id`
- `adapter_input_fields`
- `source_capture_fields`
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

## Matching Logic

R332 matches source-data rows to adapter rows by:

1. Exact `source_row_id == adapter row_id`.
2. Family mapping with `lane_key`, source adapter/capture family, and variant/capture name when IDs differ.
3. Explicit unmatched rows when either side has no counterpart.

Adapter family mapping:

- `exits` -> `exit_variant_comparison`
- `ma_wma_anchor` -> `ma_wma_anchor_enrichment`
- `review_ready_enrichment` -> `review_ready_enrichment`
- `capture_8m_short` -> `short_capture_improvement`
- `near_miss_13m` -> `near_miss_variant_capture`
- `betrayal_inverse_lab` -> `betrayal_inverse_source_chain`
- `watch_88m` -> `watch_88m_durability`

## Status Rules

- Adapter ready plus source ready becomes `MERGED_READY`.
- Source pending becomes `MERGED_PENDING_SOURCE_DATA`.
- Lab-only source or adapter becomes `MERGED_LAB_ONLY`.
- Watch-only source or adapter becomes `MERGED_WATCH_ONLY`.
- Unmatched adapter row becomes `MERGED_UNMATCHED_ADAPTER_ROW`.
- Unmatched source row becomes `MERGED_UNMATCHED_SOURCE_ROW`.

R332 does not invent source data, does not convert pending rows to ready, and does not create synthetic performance.

## Summaries

R332 emits:

- `merge_counts`
- `adapter_merge_summaries`
- `ready_merge_summary`
- `pending_merge_summary`
- `lab_only_merge_summary`
- `watch_only_merge_summary`
- `remaining_merge_gaps`

Ready summary calls out 8m short, 13m near-miss, and review-ready enrichment rows that are ready after merge. Pending summary groups rows by `source_gap_id` and keeps `do_not_fake_data=true`.

## Remaining Gaps

Expected remaining gaps include missing exit outcome comparisons, raw anchor timeseries, MAE/MFE, regime split capture, betrayal source-chain data, and 88m durability source data. These gaps remain pending, lab-only, or watch-only.

## Betrayal Lab-Only Handling

Betrayal/inverse remains:

- `MERGED_LAB_ONLY`
- `standard_55_policy_applies=false`
- `source_chain_required=true`
- `exact_risk_mapping_required=true`
- `stale_shadow_outcomes_forbidden=true`
- `live_permission=false`
- `tiny_live_eligible_now=false`

## R333 / R330 Path

Recommended R333:

```text
Strategy Lab Merged Evidence Ranking Packet
```

R333 should rank merged evidence after source-data status is attached.

Recommended R330:

```text
Human-Reviewed Observed Expansion Promotion Gate
```

R330 can later alter observed expansion only after human review.

## Tiny Live Path

Tiny Live remains separately gated. The first Tiny Live lane remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

R332 does not arm, submit, create a final command, or change live permission.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable the kill switch, mutate arming state, submit, create a final command, change the first Tiny Live lane, write promotion events, write risk contracts, mutate observed expansion, mutate config, mutate env, mutate systemd, start schedulers, send Telegram, send real Telegram, or create synthetic performance.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_captured_source_data_merge --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_captured_source_data_merge --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-captured-source-data-merge
bash scripts/hammer_print_r332_strategy_lab_captured_source_data_merge.sh
```
