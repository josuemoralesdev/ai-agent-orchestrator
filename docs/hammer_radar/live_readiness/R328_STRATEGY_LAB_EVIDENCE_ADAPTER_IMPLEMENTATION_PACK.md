# R328 Strategy Lab Evidence Adapter Implementation Pack

## Why R328 Exists

R326 mapped seven missing Strategy Lab evidence feeds. R328 implements those feeds as deterministic, read-only paper/lab adapters that produce normalized evidence rows for later batch comparison.

R328 does not promote candidates, write promotion events, write risk contracts, alter observed expansion, change Tiny Live, start schedulers, send Telegram, or execute trades.

## What R326 Mapped

R326 identified adapter feeds for:

- 13m near-miss repair
- 8m short capture improvement
- MA/WMA200 anchor confluence
- exit / TP / SL / trailing comparisons
- Betrayal/inverse lab-only source-chain evidence
- 88m watch-only durability
- 44m/55m review-ready enrichment

## Implemented Adapters

R328 implements:

- `near_miss_13m`
- `capture_8m_short`
- `ma_wma_anchor`
- `exits`
- `betrayal_inverse_lab`
- `watch_88m`
- `review_ready_enrichment`

The output ledger is:

```text
logs/hammer_radar_forward/strategy_lab_evidence_adapter_pack.ndjson
```

The event type is:

```text
R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK
```

## Normalized Evidence Row Schema

Every adapter-created row includes:

- `adapter_id`
- `row_id`
- `lane_key`
- `timeframe`
- `side`
- `entry_mode`
- `variant_family`
- `variant_name`
- `evidence_status`
- `source_chain`
- `input_fields`
- `derived_fields`
- `sample_count_source`
- `win_rate_source`
- `avg_pnl_source`
- `live_permission=false`
- `tiny_live_eligible_now=false`
- `promotion_event_written=false`
- `risk_contract_write_required=false`
- `scheduler_required=false`
- `blockers`

## Remaining Source-Data Gaps

R328 does not fake unavailable data. Rows that need future capture are marked `ADAPTER_NEEDS_SOURCE_DATA`.

Current reported gaps include:

- missing raw anchor timeseries
- missing exit outcome comparison
- missing betrayal source-chain data
- missing MAE/MFE adverse excursion fields

## Betrayal/Inverse Lab-Only Behavior

The betrayal/inverse adapter emits `LAB_ONLY` rows and preserves:

- `lab_only=true`
- `standard_55_policy_applies=false`
- `preferred_win_rate_pct=60`
- `min_sample_count=30`
- `preferred_sample_count=50`
- `avg_pnl_requirement=positive`
- `original_vs_inverse_required=true`
- `source_chain_required=true`
- `exact_risk_mapping_required=true`
- `stale_shadow_outcomes_forbidden=true`
- `live_permission=false`
- `tiny_live_eligible_now=false`

## R329/R330 Path

Recommended R329:

```text
Strategy Lab Adapter Output Batch Execution Packet
```

R329 should run comparisons over R328 normalized rows.

Recommended R330:

```text
Human-Reviewed Observed Expansion Promotion Gate
```

R330 can later alter observed expansion after human review. It must remain separate from Tiny Live authorization.

## Tiny Live Path

Tiny Live remains separately gated. R328 preserves the first Tiny Live lane:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

R328 does not arm, submit, create a final command, or change live permission.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable the kill switch, mutate arming state, submit, create a final command, change the first Tiny Live lane, write promotion events, write risk contracts, mutate observed expansion, mutate config, mutate env, mutate systemd, start schedulers, send Telegram, or send real Telegram.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-evidence-adapter-pack
bash scripts/hammer_print_r328_strategy_lab_evidence_adapter_pack.sh
```
