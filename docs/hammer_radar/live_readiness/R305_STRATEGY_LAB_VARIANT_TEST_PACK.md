# R305 Strategy Lab Variant Test Pack

R305 extends the R304 Strategy Lab preview with a paper-only variant test pack.
It ranks entry, timing, TP/SL, trailing, freshness, filter, and betrayal/inverse
opportunities from existing evidence only.

## Why This Phase Exists

R304 showed stronger preview candidates, including 44m short and 55m long lanes,
but preview strength is not live permission. R305 asks whether variants have
direct paper evidence and which missing dimensions need capture before a future
dry-run expansion review.

The current first Tiny Live lane remains unchanged:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_variant_test_pack --help
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_variant_test_pack --log-dir logs/hammer_radar_forward
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-variant-test-pack
bash scripts/hammer_print_r305_strategy_lab_variant_pack.sh
```

The output ledger is:

```text
logs/hammer_radar_forward/strategy_lab_variant_test_pack.ndjson
```

## How To Read Output

Important fields:

- `variant_candidates`: all R305 lab rows.
- `top_variant_candidates`: top direct-evidence rows by lab score.
- `top_near_miss_variant_opportunities`: near-miss rows worth paper tracking.
- `evidence_status`: `DIRECT_PAPER_EVIDENCE` or `INSUFFICIENT_DIRECT_VARIANT_EVIDENCE`.
- `variant_score_status`: scored from direct evidence or `NEEDS_PAPER_CAPTURE`.
- `strategy_lab_score`: lab-only score, not a live rank.
- `confidence_class`: paper confidence class only.
- `betrayal_inverse_lab_preview`: stricter betrayal capture status.

For variants without direct evidence, R305 sets:

```text
evidence_status=INSUFFICIENT_DIRECT_VARIANT_EVIDENCE
variant_score_status=NEEDS_PAPER_CAPTURE
recommended_lab_action=CAPTURE_VARIANT_EVIDENCE
```

## Expansion Preview Is Not Live Permission

`EXPANSION_PREVIEW_ONLY` means a lane is interesting for a future dry-run review.
It does not allow execution, final commands, autonomous arming, risk-contract
mutation, or live promotion.

R305 always reports:

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
submit_allowed=false
final_command_available=false
binance_order_endpoint_called=false
binance_test_order_endpoint_called=false
secrets_shown=false
```

## Betrayal / Inverse Rules

Betrayal and inverse candidates remain preview-only. A future review still needs:

- preferred win rate at least 60%
- minimum 30 true paper outcomes, preferred 50
- positive average PnL
- clean original-vs-inverse improvement
- complete source chain
- exact lane, entry, and risk-contract mapping
- no stale shadow evidence

R305 never emits betrayal live permission.

## Recommended R306 Paths

If direct variant evidence supports it:

```text
R306 Eligible Lane Expansion Dry-Run Preview
```

That path may review 44m short and 55m long as dry-run-only candidates, without
enabling live and without changing the current first Tiny Live lane automatically.

If direct evidence is weak:

```text
R306 Variant Evidence Capture Scheduler
```

That path should collect direct paper evidence for missing timing, TP/SL,
trailing, freshness, and filter dimensions.

## What Not To Do

- Do not promote R305 rows to live.
- Do not enable live flags.
- Do not disable the kill switch.
- Do not call Binance order, test-order, leverage, or margin endpoints.
- Do not mutate `configs/hammer_radar/autonomous_arming_state.json`.
- Do not mutate `configs/hammer_radar/tiny_live_risk_contracts.json`.
- Do not treat a lab rank as submit permission.
