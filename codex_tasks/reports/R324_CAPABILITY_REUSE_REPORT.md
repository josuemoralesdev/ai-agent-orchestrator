# R324 Capability Reuse Report

## Phase Classification

Primary classification: EXTENSION OF EXISTING CAPABILITY

Secondary classification: DIAGNOSTIC / AUDIT

Duplicate risk level: MEDIUM

Reason: R324 composes existing Strategy Lab preview, variant test pack, and expansion surface-map outputs into a structured batch runner. It overlaps with R305/R323 evidence reporting, so the implementation must reuse those sources and avoid becoming a new promotion engine.

## Existing Strategy Lab Capability Reuse

Checked docs:

- `docs/hammer_radar/live_readiness/R323_STRATEGY_LAB_EXPANSION_REENTRY_AND_CANDIDATE_SURFACE_MAP.md`
- `docs/hammer_radar/live_readiness/R305_STRATEGY_LAB_VARIANT_TEST_PACK.md`
- `docs/hammer_radar/live_readiness/R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW.md`

The prompt referenced `R304_STRATEGY_LAB_PREVIEW.md`; the repo contains the same surface under `R304_PAPER_REFRESH_DURABILITY_AND_STRATEGY_LAB_PREVIEW.md`.

Checked modules:

- `src/app/hammer_radar/operator/strategy_lab_expansion_surface_map.py`
- `src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py`
- `src/app/hammer_radar/operator/strategy_lab_preview.py`
- `src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py`
- `src/app/hammer_radar/operator/inspect.py`

Checked tests:

- `tests/hammer_radar/test_strategy_lab_expansion_surface_map.py`
- `tests/hammer_radar/test_strategy_lab_variant_test_pack.py`
- `tests/hammer_radar/test_strategy_lab_preview.py`

Checked configs and ledgers:

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `logs/hammer_radar_forward/strategy_lab_preview.ndjson`
- `logs/hammer_radar_forward/strategy_lab_variant_test_pack.ndjson`
- `logs/hammer_radar_forward/strategy_evidence_registry.ndjson`
- `logs/hammer_radar_forward/strategy_promotion_events.ndjson`

## Existing Variant Pack Reuse

R305 already builds direct and missing variant evidence rows for entry modes, timing, TP/SL, trailing, filters, and betrayal/inverse capture priorities. R324 reuses R305 output as evidence snapshots and does not recompute live eligibility or invent synthetic direct evidence.

## Existing Surface Map Reuse

R323 already maps the baseline lane, primary lanes, watch-only lanes, near-miss surface, betrayal/inverse rules, and Tiny Live path. R324 reuses those lane groups and safety semantics, then organizes them into batch groups for R325 review.

## Duplicate Risk Report

Similar existing modules:

- `strategy_lab_preview.py`
- `strategy_lab_variant_test_pack.py`
- `strategy_lab_expansion_surface_map.py`
- `eligible_lane_expansion_dry_run_preview.py`

Similar existing endpoints / inspect commands:

- `strategy-lab-preview`
- `strategy-lab-variant-test-pack`
- `eligible-lane-expansion-dry-run-preview`
- `strategy-lab-expansion-surface-map`

Similar existing scheduler tasks:

- paper refresh scheduler
- multi-lane dry-run observation scheduler

Similar existing docs:

- R304, R305, R306, and R323 live-readiness docs

Risk: MEDIUM. R324 could duplicate R305 ranking or R323 promotion summaries if it recalculates strategy quality.

Mitigation: R324 is implemented as a read-only batch organizer. It consumes existing packets, emits batch policy and blockers, and does not write promotion events, risk contracts, configs, env, arming state, systemd units, or Telegram messages.

## Why R324 Is A Batch Runner, Not A Promotion Engine

R324 groups existing and missing evidence into actionable paper/lab batches. It separates `ready_for_R325_review`, `needs_more_samples`, `watch_only`, `lab_only`, and `blocked`, but it does not authorize live execution and does not write promotion artifacts.

Promotion remains a future human-reviewed R325 concern. Risk contracts remain separate and must not be written by R324.

## How R324 Feeds R325 Promotion Review

R324 produces:

- structured batch results for eight required evidence groups
- evidence snapshots where existing R305/R323 data is available
- missing adapter notes where direct evidence needs capture
- promotion-review buckets that keep lab-only candidates separate
- explicit R325 and R326 recommendations
- Tiny Live path statements that preserve the existing baseline lane and final gate

R325 should use this packet as a review input, not as live permission.
