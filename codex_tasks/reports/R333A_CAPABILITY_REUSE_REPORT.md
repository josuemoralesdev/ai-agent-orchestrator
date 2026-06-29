# R333A Capability Reuse Report

## Phase Classification

Primary classification: `NEW CAPABILITY`

Secondary classifications: `DIAGNOSTIC / AUDIT`, `DUPLICATE RISK`

Duplicate risk level: `MEDIUM`

Reason: R333A follows the existing read-only Strategy Lab packet pattern, but the requested strategy family, 4m/8m ultra-short holding windows, leverage grid, net ROE contract, sequence-known requirement, and liquidation proximity model are not present in the current R325-R332 Strategy Lab chain.

## Capability Scan Summary

Docs checked:

- `docs/hammer_radar/live_readiness/R332_STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_INTO_ADAPTER_ROWS.md`
- `docs/hammer_radar/live_readiness/R331_STRATEGY_LAB_SOURCE_DATA_CAPTURE_ADAPTER_IMPLEMENTATION.md`
- `docs/hammer_radar/live_readiness/R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET.md`
- `docs/hammer_radar/live_readiness/R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK.md`
- `docs/hammer_radar/live_readiness/R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET.md`

Modules checked:

- `src/app/hammer_radar/operator/strategy_lab_captured_source_data_merge.py`
- `src/app/hammer_radar/operator/strategy_lab_source_data_capture_adapter.py`
- `src/app/hammer_radar/operator/strategy_lab_adapter_output_batch_execution_packet.py`
- `src/app/hammer_radar/operator/strategy_lab_evidence_adapter_pack.py`
- `src/app/hammer_radar/operator/inspect.py`

Tests checked:

- `tests/hammer_radar/test_strategy_lab_captured_source_data_merge.py`
- `tests/hammer_radar/test_strategy_lab_source_data_capture_adapter.py`
- `tests/hammer_radar/test_strategy_lab_adapter_output_batch_execution_packet.py`

Configs and ledgers checked:

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- `logs/hammer_radar_forward/strategy_lab_captured_source_data_merge.ndjson`
- `logs/hammer_radar_forward/strategy_lab_source_data_capture_adapter.ndjson`
- `logs/hammer_radar_forward/strategy_lab_adapter_output_batch_execution_packet.ndjson`
- `logs/hammer_radar_forward/strategy_lab_evidence_adapter_pack.ndjson`
- `logs/hammer_radar_forward/multi_lane_dry_run_observation.ndjson`

Existing endpoints and CLI commands checked:

- Existing Strategy Lab inspect routes for preview, variant test pack, expansion surface map, batch runner, promotion review, candidate feed expansion, evidence adapter pack, adapter output batch execution, source data capture, and captured source data merge.
- Tiny Live inspect routes and config surfaces were checked as duplicate-risk boundaries, not as reusable authorization paths.

Existing scheduler tasks checked:

- Multi-lane dry-run observation scheduler and paper refresh scheduler surfaces were checked only for safety separation. R333A does not start or mutate any scheduler.

## Why This Is New Capability

R333A introduces a separate strategy family:

```text
ULTRA_SHORT_LEVERAGE_BURST
```

No existing Strategy Lab module defines 22x/44x/88x/150x leverage modeling, 22s/44s/66s/88s/132s/176s checkpoint windows, net-after-fee/slippage burst ROE formulas, or second/tick-level sequence requirements for 4m and 8m immediate-entry paper signals.

## Why This Must Be Isolated

Tiny Live and standard Strategy Lab promotion are slower, separate safety surfaces. R333A must not inherit:

- the first Tiny Live lane
- R271 standard 55% policy
- normal Strategy Lab promotion
- observed expansion review
- betrayal/inverse lab behavior
- existing 10x live risk contracts

The burst family has materially different risk because high leverage amplifies fees, slippage, latency, and liquidation proximity.

## Reusable Signal Surfaces

Reusable surfaces include existing radar/strategy signal outputs, current Strategy Lab source-chain conventions, and read-only packet/inspect/ledger patterns. These can provide signal identity and candidate context, but they do not prove second-level burst sequencing.

## Missing Data Surfaces

Missing surfaces for R333B include exact detection timestamps, first valid paper fill timestamps, second-level or tick/trade price path, checkpoint prices, entry/exit fee assumptions, entry/exit slippage assumptions, latency measurements, max adverse excursion, max favorable excursion, and sequence-known flags.

## Why Second Or Tick-Level Data May Be Required

The proposed holds are 22s to 176s. At 150x, a 15% gross ROE needs about a 0.10% favorable price move before fees and slippage. Small intra-candle ordering differences can decide whether a row is a win, loss, liquidation danger event, or timeout.

## Why Candle-Only OHLC Is Unsafe

Candle-only OHLC cannot prove whether take profit or stop loss happened first inside a 44s or 88s burst. Candle-only rows must be marked `sequence_unknown`; `sequence_unknown` rows cannot promote to live and cannot satisfy the future evidence contract.

## Reuse / Extend / Create Decision

Existing capability reused:

- Packet build/format/load pattern.
- Inspect subcommand pattern.
- Safety flag pattern.
- Tiny Live baseline lane constant.

Existing capability extended:

- `inspect.py` gained a read-only route for the new packet.

New capability created:

- `src/app/hammer_radar/operator/ultra_short_leverage_burst_lab_design.py`
- R333A docs, shell printer, tests, and design ledger output.

Why new code was necessary:

- The requested behavior is a new isolated family and a design contract, not a standard Strategy Lab adapter row merge.

Why this is not duplicating prior work:

- R333A does not reimplement R328-R332 adapter logic. It defines a future burst lab contract and explicitly points R333B/R333C/R333D to the missing pieces.

## Duplicate Risk Report

Similar existing modules:

- Strategy Lab evidence adapter, adapter output batch packet, source data capture adapter, and captured source data merge.

Similar existing endpoints:

- Strategy Lab inspect routes and Tiny Live final gates.

Similar existing CLI commands:

- Existing `strategy-lab-*` commands.

Similar existing scheduler tasks:

- Multi-lane dry-run observation and paper refresh scheduler.

Similar existing docs:

- R325, R328, R329, R331, and R332 live readiness docs.

Risk:

- Medium. The packet could be mistaken for Strategy Lab promotion or Tiny Live readiness if not isolated.

Mitigation:

- The packet uses `strategy_family=ULTRA_SHORT_LEVERAGE_BURST`, `strategy_family_isolated=true`, `paper_only=true`, `burst_live_permission=false`, `live_permission_count=0`, no promotion writes, no risk-contract writes, no observed expansion writes, and no Tiny Live inheritance.
