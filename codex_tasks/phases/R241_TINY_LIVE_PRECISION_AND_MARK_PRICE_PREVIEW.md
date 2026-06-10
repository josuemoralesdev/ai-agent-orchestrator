# R241 Tiny-Live Precision And Mark Price Preview

## Objective

Consume the R240 non-executable order payload artifact and preview the precision, mark-price, quantity-rounding, and min-notional requirements needed before any future executable payload phase.

## Required Safety

- No Binance/network calls by default.
- Prefer local cached exchange info if present.
- No order placement.
- No test order placement.
- No executable payload creation.
- No signed order or trading request.
- No env/config/lane-control mutation.
- No kill switch disable.
- No secrets printed.

## Inputs

- `logs/hammer_radar_forward/tiny_live_order_payload_write_gate.ndjson`
- R240 non-executable artifact for `BTCUSDT|8m|short|ladder_close_50_618`
- Existing read-only cached exchange info if present

## Expected Output

Preview-only operator packet containing:

- symbol precision requirements
- price precision requirements
- quantity step-size requirements
- mark-price or candidate-price snapshot requirement
- quantity-rounding blockers
- min-notional blockers
- explicit confirmation requirements for any future executable payload phase

## Explicit Non-Actions

- Do not call Binance/network unless a separate later guarded phase authorizes read-only connectivity.
- Do not create executable payloads.
- Do not sign requests.
- Do not place orders.
