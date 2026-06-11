# R249 Tiny-Live Executable Payload Write Gate

R249 adds a guarded local executable payload artifact write gate for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

The gate consumes the recorded R248 stop/take-profit source, R247 executable payload preview, R246 refreshed non-executable payload artifact, R244 adjusted risk contract, and R242 read-only precision/mark-price record.

## Safety State

- Preview is default.
- Optional confirmed mutation is limited to `logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson`.
- The exact confirmation phrase is `I CONFIRM TINY LIVE EXECUTABLE PAYLOAD WRITE GATE ONLY; WRITE LOCAL PAYLOAD ARTIFACT ONLY; NO SIGNATURE; NO ORDER; NO BINANCE CALL.`
- The written artifact is executable-shaped and local only.
- `signed=false`.
- `submit_allowed=false`.
- `binance_call_allowed=false`.
- `network_allowed=false`.
- `order_placed=false`.
- No signed request is created.
- No Binance/network call is made.
- No order or test-order placement occurs.
- No config/env/lane-control/risk-contract write occurs.
- No kill-switch disable occurs.
- Official tiny-live lane remains unchanged.

## Validation

R249 requires:

- official lane exactly `BTCUSDT|8m|short|ladder_close_50_618`
- symbol `BTCUSDT`
- direction `short`
- main order `SELL MARKET` with quantity `0.007`
- stop order `BUY STOP_MARKET reduceOnly=true`
- take-profit order `BUY TAKE_PROFIT_MARKET reduceOnly=true`
- stop price above the R248 entry/reference price
- take-profit price below the R248 entry/reference price
- risk model `margin_budget_usdt=44`, `leverage=10`, `max_notional_usdt=440`, `max_loss_usdt=4.44`
- estimated stop loss within tick/rounding tolerance
- future signature gate and submit gate remain required

## Primary Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-executable-payload-write-gate
```

Rejected confirmation check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-executable-payload-write-gate \
  --write-executable-payload \
  --confirm-tiny-live-executable-payload-write "wrong"
```

Write local executable payload artifact only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-executable-payload-write-gate \
  --write-executable-payload \
  --confirm-tiny-live-executable-payload-write "I CONFIRM TINY LIVE EXECUTABLE PAYLOAD WRITE GATE ONLY; WRITE LOCAL PAYLOAD ARTIFACT ONLY; NO SIGNATURE; NO ORDER; NO BINANCE CALL."
```

## Next Phase

R250 should consume the R249 executable payload artifact and preview local signed request construction only. It must not write a signed request, call Binance, submit, or place an order.
