# R323 Capability Reuse Report

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification: WIRING / INTEGRATION
- Duplicate risk level: MEDIUM
- Reason: R323 overlaps R304 Strategy Lab, R305 variant pack, R306 expansion preview, R307-R309 risk-contract review, R310 observation scheduling, and R314 observation health. It should map those surfaces, not rebuild their engines.

## Existing Strategy Lab Capabilities

- R304 paper refresh and Strategy Lab preview already ranks current evidence and marks live-qualified, near-miss, paper-only, blocked, and betrayal/inverse preview rows.
- R305 Strategy Lab Variant Test Pack already builds entry, timing, TP/SL, trailing, freshness, filter, and betrayal/inverse lab rows from existing evidence.
- Existing ledgers checked:
  - `logs/hammer_radar_forward/strategy_lab_preview.ndjson`
  - `logs/hammer_radar_forward/strategy_lab_variant_test_pack.ndjson`
  - `logs/hammer_radar_forward/strategy_promotion_events.ndjson`
  - `logs/hammer_radar_forward/strategy_evidence_registry.ndjson`

## Existing Variant Test Capabilities

- `src/app/hammer_radar/operator/strategy_lab_variant_test_pack.py` already defines entry modes, timing variants, TP/SL variants, trailing variants, and filter variants.
- Existing variant output is lab-only and explicitly blocks submit, final commands, Binance order/test-order endpoints, and live permission.

## Existing Promotion And Risk-Contract Capabilities

- R306 already previews baseline, primary dry-run expansion candidates, secondary watch-only candidates, exact risk-contract status, final-gate status, timer requirements, and no-live safety fields.
- R307/R308/R309 docs and modules cover expansion risk-contract preview/repair and human-reviewed write gates.
- `configs/hammer_radar/tiny_live_risk_contracts.json` already contains tiny-live risk-contract rows for the baseline and observed expansion/watch lanes. R323 reads this file only.

## Observed Lane Capabilities

- Baseline tiny-live lane:
  - `BTCUSDT|44m|long|ladder_close_50_618`
- Primary observed expansion lanes:
  - `BTCUSDT|44m|short|ladder_382_50_618`
  - `BTCUSDT|44m|short|ladder_close_50_618`
  - `BTCUSDT|55m|long|ladder_close_50_618`
- Secondary watch-only lanes:
  - `BTCUSDT|44m|short|ladder_22_44_22`
  - `BTCUSDT|44m|long|ladder_382_50_618`
  - `BTCUSDT|55m|long|market_close`
  - `BTCUSDT|88m|long|ladder_382_50_618`

## Duplicate Risk Report

- Similar modules:
  - `strategy_lab_preview.py`
  - `strategy_lab_variant_test_pack.py`
  - `eligible_lane_expansion_dry_run_preview.py`
  - `expansion_risk_contract_preview_repair.py`
  - `multi_lane_observation_health_panel.py`
- Similar endpoints/inspect commands:
  - `strategy-lab-preview`
  - `strategy-lab-variant-test-pack`
  - `eligible-lane-expansion-dry-run-preview`
  - `multi-lane-observation-health-panel`
- Similar docs:
  - R304, R305, R306, R307, R308, R309, R310, R314, R322 live-readiness docs.
- Risk: creating another ranking engine would duplicate existing scoring and increase promotion ambiguity.
- Mitigation: R323 composes existing outputs, summarizes lane/risk/evidence state, and recommends R324 batch groups. It does not create scoring, execute trades, mutate risk contracts, or promote lanes.

## Why R323 Is A Map, Not A New Engine

R323 answers operator questions across existing surfaces: what exists, what is observed, what is watch-only, what has contracts, what needs samples, what remains lab-only, and what R324 should batch next. It does not detect signals, generate orders, change strategy scoring, mutate arming, write risk contracts, or enable live execution.

## How R323 Guides R324

R323 recommends `R324 Strategy Lab Variant Batch Runner` with concrete batch groups:

1. 44m short variants
2. 55m long variants
3. 13m near-miss repair variants
4. 8m short capture-improvement variants
5. 88m watch-only evidence variants
6. Betrayal/inverse lab-only variants
7. MA/WMA200 anchor variants
8. exit/TP/SL/trailing variants

R324 should generate more candidate surface and direct evidence while preserving all Tiny Live gates.

## Safety

R323 must always report no live mutation:

- `live_execution_enabled=false`
- `allow_live_orders=false`
- `global_kill_switch=true`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `submit_allowed=false`
- `final_command_available=false`
- `real_order_forbidden=true`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `leverage_change_called=false`
- `margin_change_called=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`
- `autonomous_arming_state_changed=false`
- `global_live_flags_changed=false`
- `risk_contract_config_mutated=false`
- `config_written=false`
- `env_written=false`
- `env_mutated=false`
- `systemd_unit_mutated=false`
- `scheduler_started=false`
- `telegram_send_called=false`
- `telegram_message_sent=false`
- `real_telegram_send_called=false`
- `real_telegram_message_sent=false`
