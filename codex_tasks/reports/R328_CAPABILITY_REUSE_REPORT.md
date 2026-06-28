# R328 Capability Reuse Report

## Phase Classification

Primary classification: `EXTENSION OF EXISTING CAPABILITY`

Secondary classification: `WIRING / INTEGRATION`

Duplicate risk level: `MEDIUM`

Reason: R326 already defined the seven adapter feeds and R324/R325 already expose Strategy Lab evidence packets. R328 should implement the missing adapter row builders and wiring without duplicating promotion, risk-contract, scheduler, or Tiny Live behavior.

## Existing Docs Checked

- `docs/hammer_radar/live_readiness/R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS.md`
- `docs/hammer_radar/live_readiness/R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET.md`
- `docs/hammer_radar/live_readiness/R324_STRATEGY_LAB_VARIANT_BATCH_RUNNER.md`
- `docs/hammer_radar/live_readiness/R305_STRATEGY_LAB_VARIANT_TEST_PACK.md`
- `docs/hammer_radar/live_readiness/R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW.md`

## Existing Modules Checked

- `src/app/hammer_radar/operator/strategy_lab_candidate_feed_expansion.py`
- `src/app/hammer_radar/operator/strategy_lab_promotion_review_packet.py`
- `src/app/hammer_radar/operator/strategy_lab_variant_batch_runner.py`
- `src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py`
- `src/app/hammer_radar/operator/strategy_lab_preview.py`
- `src/app/hammer_radar/operator/paper_refresh_scheduler.py`
- `src/app/hammer_radar/operator/inspect.py`

## Existing Tests Checked

- `tests/hammer_radar/test_strategy_lab_candidate_feed_expansion.py`
- `tests/hammer_radar/test_strategy_lab_promotion_review_packet.py`
- `tests/hammer_radar/test_strategy_lab_variant_batch_runner.py`
- `tests/hammer_radar/test_strategy_lab_variant_test_pack.py`

## Existing Logs And Ledgers Checked

- `logs/hammer_radar_forward/strategy_lab_candidate_feed_expansion.ndjson`
- `logs/hammer_radar_forward/strategy_lab_promotion_review_packet.ndjson`
- `logs/hammer_radar_forward/strategy_lab_variant_batch_runner.ndjson`
- `logs/hammer_radar_forward/strategy_lab_variant_test_pack.ndjson`
- `logs/hammer_radar_forward/strategy_evidence_registry.ndjson`

## Existing Feed Map Reuse

R328 reuses R326 feed IDs and candidate lanes:

- `near_miss_13m`
- `capture_8m_short`
- `ma_wma_anchor`
- `exits`
- `betrayal_inverse_lab`
- `watch_88m`
- `review_ready_enrichment`

R326 remains the map. R328 is the implementation layer that turns the mapped feeds into normalized rows.

## Existing Strategy Lab Packet Reuse

R328 consumes current packet shapes from:

- R326 candidate feed expansion for adapter IDs and lane scope
- R325 promotion review packet for review-ready, near-miss, watch-only, and lab-only candidate context
- R324 variant batch runner for evidence snapshots, sample counts, win rates, average PnL, and source chains

R328 does not re-score promotion candidates and does not change the first Tiny Live lane.

## Existing Evidence Registry Reuse

The existing `strategy_evidence_registry.ndjson` defines paper-only evidence families, source identity requirements, and betrayal/anchor safety defaults. R328 references it as a source surface and preserves lab-only betrayal semantics. R328 does not write the registry.

## Duplicate Risk Report

Similar existing modules:

- R326 maps feed packets but does not build adapter rows.
- R324 groups batch surfaces but does not normalize adapter output rows.
- R305 builds variant test rows but does not implement the R326 adapter pack.
- R304 previews Strategy Lab evidence but does not prepare R329 adapter comparison inputs.

Similar existing endpoints:

- `strategy-lab-preview`
- `strategy-lab-variant-test-pack`
- `strategy-lab-variant-batch-runner`
- `strategy-lab-promotion-review-packet`
- `strategy-lab-candidate-feed-expansion`

Similar existing CLI commands:

- `python -m src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion`
- `python -m src.app.hammer_radar.operator.strategy_lab_promotion_review_packet`
- `python -m src.app.hammer_radar.operator.strategy_lab_variant_batch_runner`
- `python -m src.app.hammer_radar.operator.strategy_lab_variant_test_pack`

Similar existing scheduler tasks:

- `paper_refresh_scheduler` exists for paper-side refresh health.
- R328 does not implement or start schedulers.

Similar existing docs:

- R326 defines the missing adapter map.
- R325 defines review and live separation.
- R324 defines batch group separation.
- R305 defines variant test pack behavior.

Risk: `MEDIUM`, because R328 is close to R326/R324/R325 shapes.

Mitigation: R328 reuses their constants, statuses, packet records, safety fields, formatter pattern, inspect wiring, and shell script pattern while writing only `strategy_lab_evidence_adapter_pack.ndjson`.

## Why R328 Implements Adapters But Not Schedulers

R328's job is to make deterministic adapter rows from current Strategy Lab packets and observed lane evidence. It can report `ADAPTER_NEEDS_SOURCE_DATA` when raw anchor timeseries, exit comparison outcomes, betrayal source-chain data, or MAE/MFE are missing.

Schedulers would be a separate capture phase because they mutate runtime behavior and collect new data over time. R328 remains read-only except for its own optional output ledger.

## How R328 Feeds R329 Batch Execution

R328 produces normalized rows with stable `adapter_id`, `row_id`, lane, variant, input fields, derived fields, source-chain, evidence status, and safety fields. R329 can consume `strategy_lab_evidence_adapter_pack.ndjson` and run comparison batches over those rows without rereading every upstream packet shape.

R329 should compare adapter dimensions, source-data gaps, and row readiness. R330 can later alter observed expansion only after human review. Tiny Live remains separately gated.
