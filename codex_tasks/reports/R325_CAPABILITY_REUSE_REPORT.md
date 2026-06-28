# R325 Capability Reuse Report

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classifications: WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: MEDIUM
- Reason: R325 summarizes R323/R324/R306-R309 outputs. It resembles promotion, risk-contract, and Tiny Live gate surfaces, so it must remain a review packet only.

## Existing Docs Checked

- `docs/hammer_radar/live_readiness/R324_STRATEGY_LAB_VARIANT_BATCH_RUNNER.md`
- `docs/hammer_radar/live_readiness/R323_STRATEGY_LAB_EXPANSION_REENTRY_AND_CANDIDATE_SURFACE_MAP.md`
- `docs/hammer_radar/live_readiness/R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R307_EXPANSION_RISK_CONTRACT_PREVIEW_REPAIR.md`
- `docs/hammer_radar/live_readiness/R308_EXPANSION_RISK_CONTRACT_WRITE_GATE_PREVIEW.md`
- `docs/hammer_radar/live_readiness/R309_HUMAN_REVIEWED_RISK_CONTRACT_WRITE_GATE.md`

## Existing Modules Checked

- `src/app/hammer_radar/operator/strategy_lab_variant_batch_runner.py`
- `src/app/hammer_radar/operator/strategy_lab_expansion_surface_map.py`
- `src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py`
- `src/app/hammer_radar/operator/expansion_risk_contract_preview_repair.py`
- `src/app/hammer_radar/operator/inspect.py`

## Existing Tests Checked

- `tests/hammer_radar/test_strategy_lab_variant_batch_runner.py`
- `tests/hammer_radar/test_strategy_lab_expansion_surface_map.py`
- `tests/hammer_radar/test_eligible_lane_expansion_dry_run_preview.py`
- `tests/hammer_radar/test_expansion_risk_contract_preview_repair.py`

## Existing Logs, Ledgers, And Configs Checked

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `logs/hammer_radar_forward/strategy_lab_variant_batch_runner.ndjson`
- `logs/hammer_radar_forward/strategy_lab_expansion_surface_map.ndjson`
- `logs/hammer_radar_forward/strategy_promotion_events.ndjson`
- `logs/hammer_radar_forward/strategy_evidence_registry.ndjson`

## Reuse Decision

R325 reuses R324 as the candidate bucket source:

- `ready_for_R325_review`
- `needs_more_samples`
- `watch_only`
- `lab_only`
- `blocked`

R325 reuses R323 as the surface and current Tiny Live status source, including observed primary lanes, secondary watch lanes, Telegram scope, and the first Tiny Live baseline lane.

R325 reuses R306/R307/R308/R309 separation rules:

- R306: dry-run expansion preview does not authorize live.
- R307: missing risk-contract preview templates are not written.
- R308: write-gate preview is not an apply path.
- R309: risk-contract writes require a separate explicit human-reviewed gate.

R325 creates a new module because the requested output contract is a different operator artifact: a human-readable promotion review packet. It does not duplicate promotion writers, risk-contract writers, arming gates, Tiny Live authorization gates, or Telegram send gates.

## Duplicate Risk Report

- Similar existing modules: R323 surface map, R324 batch runner, R306 expansion preview, R307 risk-contract preview repair.
- Similar existing endpoints: `strategy-lab-expansion-surface-map`, `strategy-lab-variant-batch-runner`, `eligible-lane-expansion-dry-run-preview`, `expansion-risk-contract-preview-repair`.
- Similar existing CLI commands: same as endpoints above through `inspect`.
- Similar scheduler tasks: multi-lane dry-run observation scheduler and timer previews; R325 does not start or mutate schedulers.
- Similar docs: R323/R324 candidate surface docs and R306-R309 risk-contract docs.
- Risk: A review-ready candidate could be mistaken for promotion or live approval.
- Mitigation: Every R325 candidate has `live_permission=false`, `tiny_live_eligible_now=false`, `human_review_required=true`, and Tiny Live blockers. Packet-level safety flags also keep promotion writes, risk-contract writes, config/env/systemd mutations, Binance calls, final command, submit, and Telegram sends false.

## Why R325 Is Review Only

R325 answers which candidates are ready for human promotion review and which still need evidence, observation review, or lab-only treatment. It does not write `strategy_promotion_events.ndjson`, does not write `tiny_live_risk_contracts.json`, does not mutate arming state, does not alter Tiny Live, and does not create final commands or executable payloads.

## R326/R327 Feed

R325 feeds R326 by identifying evidence gaps for candidate feed expansion: near-miss repair, anchor variants, exit variants, and lab-only Betrayal/inverse source-chain work.

R325 feeds R327 by naming lanes that may deserve a later human-reviewed observed expansion gate. R327 would be about observed expansion only. Tiny Live remains separately gated by real candidate detection, risk contracts, human approval, and final gate clearance.
