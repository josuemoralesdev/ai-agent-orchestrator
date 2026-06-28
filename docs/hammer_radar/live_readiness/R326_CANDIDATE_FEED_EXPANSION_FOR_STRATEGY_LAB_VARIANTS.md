# R326 Candidate Feed Expansion For Strategy Lab Variants

## Why R326 Exists

R325 produced a read-only Strategy Lab promotion review packet. It confirmed that review-ready candidates exist, no promotion was written, no risk contracts were written, the first Tiny Live lane remains `BTCUSDT|44m|long|ladder_close_50_618`, and Tiny Live still waits for real candidate detection.

R326 is the next read-only planning layer. It defines the evidence-feed adapters needed before later human review or deeper batch execution.

## What R325 Decided

Review-ready candidates:

- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_22_44_22`
- `BTCUSDT|55m|long|ladder_close_50_618`
- `BTCUSDT|55m|long|market_close`

Needs more evidence or repair:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|13m|short|ladder_close_50_618`
- `BTCUSDT|8m|short|ladder_close_50_618`

Watch-only:

- `BTCUSDT|88m|long|ladder_382_50_618`

Lab-only:

- `BETRAYAL_INVERSE_LANES`

## Feed Packets

R326 emits seven feed packets:

1. `near_miss_13m`: timing repair, partial entry, early/late exit, RSI/regime filter, MA/WMA anchor, and golden-pocket context for 13m long/short repair.
2. `capture_8m_short`: faster capture, tighter invalidation, partial exit, trailing, regime filter, and entry timing for the 8m short near-threshold lane.
3. `ma_wma_anchor`: WMA200, MA200, close-vs-anchor, anchor slope, and golden-pocket confluence fields for review-ready, near-miss, and watch lanes.
4. `exits`: fixed TP/SL, early exit, late exit, trailing, partial exit, and invalidation tightening comparison artifacts.
5. `betrayal_inverse_lab`: lab-only source-chain and original-vs-inverse evidence.
6. `watch_88m`: durability, slow confirmation, HTF bias, exit variants, and anchor filters for the 88m watch-only lane.
7. `review_ready_enrichment`: stability, regime split, adverse excursion, exit sensitivity, and anchor confluence for 44m/55m review-ready candidates.

## Adapter Gaps

Missing adapters are planning-only in R326:

- `near_miss_variant_capture_adapter`
- `short_capture_improvement_adapter`
- `ma_wma_anchor_enrichment_adapter`
- `exit_variant_comparison_adapter`
- `betrayal_inverse_source_chain_adapter`
- `watch_88m_durability_adapter`
- `review_ready_enrichment_adapter`

R326 does not implement schedulers and does not start any capture service.

## Betrayal/Inverse Lab-Only Feed

Betrayal/inverse remains lab-only:

- `lab_only=true`
- `standard_55_policy_applies=false`
- `live_permission=false`
- `tiny_live_eligible_now=false`
- original-vs-inverse comparison is required
- source chain is required
- exact risk mapping is required
- stale shadow outcomes are forbidden
- preferred win rate is 60%
- minimum sample count is 30, preferred sample count is 50
- average PnL must be positive

## R327/R328 Path

Recommended R327:

```text
Human-Reviewed Observed Expansion Promotion Gate
```

R327 can alter observed expansion only after human review. It still must not authorize live execution.

Recommended R328:

```text
Strategy Lab Evidence Adapter Implementation Pack
```

R328 can implement actual evidence adapters from the R326 feed map. R328/R329 can then run deeper batches from real captured evidence.

## Tiny Live Path

Tiny Live remains separately gated. R326 does not change the first Tiny Live lane, does not arm, does not submit, and does not create a final command. Tiny Live still waits for a real candidate.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable the kill switch, mutate arming state, submit, create a final command, change the first Tiny Live lane, write promotion events, write risk contracts, mutate observed expansion, mutate config, mutate env, mutate systemd, start schedulers, send Telegram, or send real Telegram.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-candidate-feed-expansion
bash scripts/hammer_print_r326_strategy_lab_candidate_feed_expansion.sh
```

Output ledger:

```text
logs/hammer_radar_forward/strategy_lab_candidate_feed_expansion.ndjson
```
