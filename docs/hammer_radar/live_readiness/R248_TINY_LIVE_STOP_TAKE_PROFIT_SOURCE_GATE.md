# R248 Tiny-Live Stop / Take-Profit Source Gate

R248 adds a guarded preview/record gate for final stop and take-profit source levels on the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

The gate reads local records only. It prefers stop/take-profit source fields from R247, then R246/R245, then R238. If no explicit local entry/stop/take-profit source exists, it returns `TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_GATE_BLOCKED` with `TINY_LIVE_STOP_TAKE_PROFIT_SOURCE_BLOCKED_BY_MISSING_SOURCE`.

## Safety State

- Preview is default.
- Optional confirmed mutation is limited to `logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson`.
- The exact confirmation phrase is `I CONFIRM TINY LIVE STOP TAKE PROFIT SOURCE PREVIEW RECORDING ONLY; NO EXECUTABLE PAYLOAD; NO ORDER; NO BINANCE CALL.`
- No executable payload artifact writes.
- No signed requests.
- No Binance/network calls.
- No order or test-order placement.
- No config/env/lane-control/risk-contract writes.
- No kill-switch disable.
- Official tiny-live lane remains unchanged.

## Validation

For the short lane, R248 requires:

- `entry_reference_price > 0`
- stop price above entry reference
- take-profit price below entry reference
- stop side `BUY` and reduce-only
- take-profit side `BUY` and reduce-only
- stop and take-profit prices rounded with the R242 tick size
- loss preview compatible with `max_loss_usdt=4.44`
- risk/reward preview close to `2.0`

R248 does not invent stop or take-profit prices from mark price. R242 precision is used for rounding validation only.

## Primary Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-stop-take-profit-source-gate
```

Rejected confirmation check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-stop-take-profit-source-gate \
  --record-stop-take-profit-source-preview \
  --confirm-tiny-live-stop-take-profit-source-preview "wrong"
```

Record preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-stop-take-profit-source-gate \
  --record-stop-take-profit-source-preview \
  --confirm-tiny-live-stop-take-profit-source-preview "I CONFIRM TINY LIVE STOP TAKE PROFIT SOURCE PREVIEW RECORDING ONLY; NO EXECUTABLE PAYLOAD; NO ORDER; NO BINANCE CALL."
```

## Current Local Production State

The current local R246/R247 ledgers contain stop/take-profit placeholders with `null` prices. Until an explicit local stop/take-profit source is present, the gate blocks by missing source and R249 must not proceed.

## Next Phase

R249 should consume a recorded R248 stop/take-profit source gate and the recorded R247 executable payload preview. It may write an executable payload artifact only under its own exact confirmation and must still forbid signing, Binance/network calls, submit, and order placement.
