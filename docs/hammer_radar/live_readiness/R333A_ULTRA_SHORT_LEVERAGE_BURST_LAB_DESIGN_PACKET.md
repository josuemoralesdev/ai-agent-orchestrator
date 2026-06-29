# R333A Ultra Short Leverage Burst Lab Design Packet

## Why R333A Exists

R333A defines a deterministic, read-only lab contract for a distinct ultra-short, high-leverage paper strategy family. It is a design packet only. It does not implement the backtest engine, does not render the visual terminal, and does not grant live permission.

The hypothesis is narrow: open a paper position immediately when a valid 4m or 8m signal appears, evaluate very short checkpoint windows, and measure net ROE after fees and slippage rather than gross fantasy ROE.

Output ledger:

```text
logs/hammer_radar_forward/ultra_short_leverage_burst_lab_design.ndjson
```

Event type:

```text
R333A_ULTRA_SHORT_LEVERAGE_BURST_LAB_DESIGN_PACKET
```

## Separate Strategy Family

The family is:

```text
ULTRA_SHORT_LEVERAGE_BURST
```

This is isolated from Tiny Live, the R271 standard 55% policy, normal Strategy Lab promotion, observed expansion, betrayal/inverse gates, and existing 10x live risk contracts.

## Candidate Timeframes

- `4m`
- `8m`

Candidate mode is paper-only and burst-lab-only. There is no standard promotion, no Tiny Live permission, and no observed expansion write.

## Leverage And Checkpoint Grids

Leverage grid:

- `22x`
- `44x`
- `88x`
- `150x`

Required formula:

```text
price_move_pct_for_gross_roe = gross_roe_pct / leverage
```

Example: 15% gross ROE at 150x requires about 0.10% favorable price move before fees and slippage.

Checkpoint grid:

- `22s`
- `44s`
- `66s`
- `88s`
- `132s`
- `176s`

The first 44s checkpoint is the primary operator concept. 66s and 88s are second-wave checks. 22s increments are optional micro-checks. The design includes hard timeout exit, early take profit, and adverse velocity exit.

## Exit Policy

Gross ROE target grid:

- `5%`
- `10%`
- `15%`
- `22%`

Minimum net ROE target grid:

- `2%`
- `3%`
- `5%`
- `8%`

Hard loss ROE grid:

- `-5%`
- `-8%`
- `-10%`
- `-12%`

Timeout grid:

- `44s`
- `66s`
- `88s`
- `132s`
- `176s`

No averaging down is allowed. A second entry requires a new independent signal. Gross-only success classification is forbidden.

## Net ROE, Fees, And Slippage

Gross ROE is insufficient. Future rows must include net ROE after round-trip maker/taker assumptions, entry and exit slippage, and separate latency modeling.

Formula fields:

```text
notional_fee_pct_round_trip = entry_fee_pct + exit_fee_pct
fee_drag_roe = notional_fee_pct_round_trip * leverage
estimated_slippage_roe = estimated_slippage_pct_round_trip * leverage
net_roe = gross_roe - fee_drag_roe - estimated_slippage_roe
```

Unknown fees or slippage lower confidence. A burst candidate must never be marked ready using gross ROE only.

## Liquidation Proximity Warning

Liquidation proximity must be modeled. 150x requires an explicit danger-zone warning because the adverse move tolerance is microscopic. Any future tiny-burst-live preview must use microscopic sizing and isolated margin only. Cross margin is forbidden. R333A through R333D grant no live permission.

## Required Market Data

Best data is tick/trade data or second-level mark/last price. Sub-minute replay is acceptable for early lab if available. Candle-only OHLC is poor evidence for this family.

Candle-only OHLC cannot prove whether TP or SL happened first inside a 44s or 88s burst. Candle-only rows must be marked `sequence_unknown`, and `sequence_unknown` rows cannot promote to live.

## Evidence Contract

Any future promotion from burst paper lab to any live preview requires:

- sample count >= 100 minimum per side/timeframe/leverage/exit profile
- preferred sample count >= 300
- net win rate after fees/slippage >= 60%
- profit factor > 1.3
- known max adverse excursion
- known timeout behavior
- fee, slippage, latency, and liquidation proximity models
- `sequence_known=true` preferred
- no gross-only ROE readiness
- no candle-only fantasy fills
- no stale shadow outcomes
- no standard 55% policy
- no Tiny Live inheritance
- separate human-reviewed burst risk contract required

## Visual Terminal Concept

R333C should define a terminal panel, not a website. Required blocks include leverage ladder, checkpoint timeline, net ROE bars, fee drag warning, liquidation proximity warning, verdict line, paper-only/live-permission line, and reason codes.

Preview:

```text
ULTRA BURST LAB - BTCUSDT
Signal TF / side / age: 4m or 8m / long|short / measured_seconds
Entry mode: instant paper
Leverage grid: 22x / 44x / 88x / 150x
Checkpoints: 22s | 44s | 66s | 88s | 132s | 176s
Verdict: DESIGN_ONLY_NO_LIVE_PERMISSION
Live Permission: FALSE
```

## Future Phase Plan

- R333B: Ultra-Short Burst Backtest Adapter
- R333C: Ultra-Short Burst Visual Terminal Panel
- R333D: Human-Reviewed Burst Risk Contract Preview
- R333E: Burst Lab Evidence Audit And Anti-Fantasy Fill Gate
- R333F: Tiny Burst Live Activation Gate, only if the evidence contract passes

## Tiny Live Separation

The first Tiny Live lane remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

R333A does not arm, submit, create a final command, change live permission, or inherit Tiny Live approval.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable the kill switch, mutate arming state, submit, create a final command, change the first Tiny Live lane, write promotion events, write risk contracts, mutate observed expansion, mutate config, mutate env, mutate systemd, start schedulers, send Telegram, send real Telegram, or create synthetic performance.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_leverage_burst_lab_design --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_leverage_burst_lab_design --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward ultra-short-leverage-burst-lab-design
bash scripts/hammer_print_r333a_ultra_short_leverage_burst_lab_design.sh
```
