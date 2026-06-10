# R243 Tiny-Live Leverage / Notional Adjustment Preview

R243 previews a risk-model reconciliation for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It consumes the latest local R242 Binance public read-only precision / mark-price result and local R240/R238/R236/R230/R228 artifacts. It does not call Binance, does not mutate configs or env, does not create executable payloads, does not sign requests, and does not place orders.

## Purpose

R242 showed that the written R230 model treats `44` as total notional at `1x`. With BTCUSDT `step_size=0.001`, `min_notional=50`, and mark price around `62k`, the current model rounds quantity to `0.0 BTC` and fails min-notional after rounding.

The operator intent is different:

- `44 USDT` is the intended margin budget.
- `10x` leverage implies about `440 USDT` max notional.
- `440 USDT` notional should clear BTCUSDT step size and min-notional checks at the R242 mark price.

R243 previews that adjustment only. R244 is required before any risk-contract config write.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-leverage-notional-adjustment-preview
```

Record the preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-leverage-notional-adjustment-preview \
  --record-adjustment-preview \
  --confirm-tiny-live-leverage-notional-adjustment-preview "I CONFIRM TINY LIVE LEVERAGE NOTIONAL ADJUSTMENT PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

`logs/hammer_radar_forward/tiny_live_leverage_notional_adjustment_preview.ndjson`

## Safety

R243 is preview-only:

- No Binance/network calls.
- No config/env/lane-control writes.
- No risk-contract config write.
- No order payload mutation or executable payload creation.
- No signed request.
- No order or test order.
- No kill switch disable.
- No official lane change.

## Next Phase

R244 should consume a reviewed R243 preview and provide a guarded risk-contract write gate. R244 must require an exact operator confirmation phrase and must remain limited to the risk-contract config/artifact write, with no Binance/network calls, executable payload, signed request, or order.
