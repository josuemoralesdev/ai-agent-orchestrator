# R246 Tiny-Live Order Payload Refresh Write Gate

R246 writes the refreshed non-executable tiny-live order payload artifact for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It consumes the recorded R245 payload refresh preview, the R244 adjusted risk contract write gate, the R242 read-only precision/mark-price result, and the existing R240 non-executable payload artifact. Preview is default; writing requires the exact R246 confirmation phrase.

## Safety State

- Confirmed mutation is limited to `logs/hammer_radar_forward/tiny_live_order_payload_refresh_write_gate.ndjson`.
- The written artifact is ledger-only and non-executable.
- No config writes.
- No env writes.
- No lane-control writes.
- No Binance/network calls.
- No signed requests.
- No executable payloads.
- No submit-ready payloads.
- No order placement.
- Kill switch remains active.

## Primary Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-refresh-write-gate
```

Rejected confirmation check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-refresh-write-gate \
  --write-payload-refresh \
  --confirm-tiny-live-order-payload-refresh-write "wrong"
```

Write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-order-payload-refresh-write-gate \
  --write-payload-refresh \
  --confirm-tiny-live-order-payload-refresh-write "I CONFIRM TINY LIVE ORDER PAYLOAD REFRESH WRITE GATE ONLY; WRITE NON-EXECUTABLE PAYLOAD ARTIFACT ONLY; NO ORDER; NO BINANCE CALL."
```

## Expected Artifact

- `order_payload_version=tiny_live_refreshed_non_executable_payload_v1`
- `quantity=0.007`
- `notional_after_rounding=435.4721` for the current recorded R242 sample
- `margin_budget_usdt=44`
- `leverage=10`
- `notional_cap_usdt=440`
- `max_loss_usdt=4.44`
- `executable=false`
- `signed=false`
- `submit_allowed=false`
- `binance_call_allowed=false`
- `network_allowed=false`
- `order_placed=false`

## Next Phase

Recommended next engineering move:

`R247 Tiny-Live Executable Payload Preview`

R247 should consume the R246 refreshed non-executable payload artifact and preview executable payload requirements only. It must require final stop/take-profit level readiness and must not create a signed request, call Binance, submit, or place an order.
