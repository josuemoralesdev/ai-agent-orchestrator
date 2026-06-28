# R323 Strategy Lab Expansion Re-entry And Candidate Surface Map

## Why R323 Exists

R322 completed the final Telegram activation packet. Telegram alerting is now complete enough for widened observation safety, so the project can return to the core Strategy Lab objective: more lanes, more entry modes, more variants, more candidate surface, more valid signals, and Tiny Live readiness.

R323 is read-only. It maps existing Strategy Lab, expansion, observation, and risk-contract surfaces into one operator packet.

## What Telegram Completion Enables

Telegram completion improves operator visibility for observation, but it does not authorize live execution. R323 preserves paper/live separation and treats alerting as a safety surface, not a live trading gate.

## Current Surface

Baseline Tiny Live lane:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

Primary observed lanes:

```text
BTCUSDT|44m|short|ladder_382_50_618
BTCUSDT|44m|short|ladder_close_50_618
BTCUSDT|55m|long|ladder_close_50_618
```

Secondary watch-only lanes:

```text
BTCUSDT|44m|short|ladder_22_44_22
BTCUSDT|44m|long|ladder_382_50_618
BTCUSDT|55m|long|market_close
BTCUSDT|88m|long|ladder_382_50_618
```

## What Is Already Observed

R323 reuses R306 lane packets for baseline, primary dry-run expansion candidates, and secondary watch-only candidates. It also reads `configs/hammer_radar/tiny_live_risk_contracts.json` to report exact contract presence, max loss, leverage, margin budget, and notional caps.

## What Needs More Lab Work

Near-miss and capture-improvement work remains paper/lab only:

- 13m long/short near-miss repair
- 8m short capture improvement
- 88m watch-only durability
- MA/WMA200 anchor variants
- exit, TP/SL, and trailing variants

## Betrayal / Inverse Rules

Betrayal/inverse remains lab-only. R323 must not promote it to Tiny Live and must not treat it as covered by standard 55% Tiny Live policy.

Future Betrayal Lab Gate requirements:

- win rate >= 60 preferred
- sample_count >= 30 minimum, 50 preferred
- avg PnL positive
- original-vs-inverse comparison
- complete signal origin/source chain
- exact lane/entry/risk mapping
- no stale shadow outcomes
- beats normal candidates cleanly

## How R324 Should Proceed

Recommended next phase:

```text
R324 Strategy Lab Variant Batch Runner
```

Batch groups:

1. 44m short variants
2. 55m long variants
3. 13m near-miss repair variants
4. 8m short capture-improvement variants
5. 88m watch-only evidence variants
6. Betrayal/inverse lab-only variants
7. MA/WMA200 anchor variants
8. exit/TP/SL/trailing variants

## Tiny Live Distance

First Tiny Live remains baseline 44m long unless explicitly changed later. More lanes increase signal surface but do not automatically become live. Expanded lanes require evidence, risk contract, human review, and final gate clearance before future Tiny Live consideration.

Tiny Live remains waiting for real candidate detection and final gate clearance.

## What Not To Mutate

R323 must not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, mutate kill switches, mutate autonomous arming, write risk contracts, mutate configs, mutate env files, mutate systemd, start schedulers, send Telegram, submit final commands, or change the first Tiny Live lane.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_expansion_surface_map --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_expansion_surface_map --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-expansion-surface-map
bash scripts/hammer_print_r323_strategy_lab_expansion_surface_map.sh
```

Output ledger:

```text
logs/hammer_radar_forward/strategy_lab_expansion_surface_map.ndjson
```
