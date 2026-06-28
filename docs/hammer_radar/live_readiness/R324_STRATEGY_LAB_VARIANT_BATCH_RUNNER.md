# R324 Strategy Lab Variant Batch Runner

## Why R324 Exists

R323 mapped the Strategy Lab candidate surface after Telegram completion. R324 turns that map into a structured read-only batch packet for more lanes, entry modes, strategy variants, candidate surface, signals, and future Tiny Live readiness evidence.

R324 does not promote anything to live, does not write risk contracts, does not alter the first Tiny Live lane, and does not mutate live flags, configs, env, arming state, systemd, schedulers, or Telegram state.

## What R323 Mapped

Baseline first Tiny Live lane:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

Promotion-ready / primary observed lanes:

```text
BTCUSDT|44m|short|ladder_382_50_618
BTCUSDT|44m|short|ladder_close_50_618
BTCUSDT|55m|long|ladder_close_50_618
```

Watch-only and repair surface:

```text
BTCUSDT|44m|short|ladder_22_44_22
BTCUSDT|44m|long|ladder_382_50_618
BTCUSDT|55m|long|market_close
BTCUSDT|88m|long|ladder_382_50_618
BTCUSDT|13m|long|ladder_close_50_618
BTCUSDT|13m|short|ladder_close_50_618
BTCUSDT|8m|short|ladder_close_50_618
```

## Batch Groups

R324 emits eight batch groups:

1. 44m short variants
2. 55m long variants
3. 13m near-miss repair variants
4. 8m short capture-improvement variants
5. 88m watch-only evidence variants
6. Betrayal/inverse lab-only variants
7. MA/WMA200 anchor variants
8. exit/TP/SL/trailing variants

Each batch includes candidate lanes, variants to test, available evidence snapshots, sample-count policy, promotion policy, blockers, and the next recommended paper/lab action.

## Promotion Separation

R324 separates candidates into:

- `ready_for_R325_review`
- `needs_more_samples`
- `watch_only`
- `lab_only`
- `blocked`

R324 never writes promotion events. The output is evidence organization for R325, not a promotion engine.

## Betrayal / Inverse Lab-Only Rule

Betrayal/inverse remains lab-only:

- `lab_only=true`
- `tiny_live_eligible_now=false`
- `standard_55_policy_applies=false`
- preferred win rate is 60%
- minimum sample count is 30, preferred 50
- average PnL must be positive
- original-vs-inverse comparison is required
- source chain is required
- exact lane/entry/risk mapping is required
- stale shadow outcomes are forbidden

## How R325 Should Use This

R325 should consume the R324 packet as a promotion review input. It should review only non-lab-only candidates, verify direct evidence quality, preserve sample and win-rate thresholds, and keep risk-contract review separate from promotion review.

Recommended next phase:

```text
R325 Strategy Lab Promotion Review Packet
```

## Tiny Live Path

First Tiny Live remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

Expanded lanes increase candidate surface but do not become live automatically. Future live candidates require evidence, risk contract, human review, and final gate clearance. The current final gate still waits for real candidate detection.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable the kill switch, mutate arming state, issue final commands, submit, change the first Tiny Live lane, write risk contracts, write configs, write env, mutate systemd, start schedulers, send Telegram, or send real Telegram.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_variant_batch_runner --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_variant_batch_runner --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-variant-batch-runner
bash scripts/hammer_print_r324_strategy_lab_variant_batch_runner.sh
```

Output ledger:

```text
logs/hammer_radar_forward/strategy_lab_variant_batch_runner.ndjson
```
