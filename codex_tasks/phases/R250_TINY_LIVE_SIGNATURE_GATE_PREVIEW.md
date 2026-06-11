# R250 Tiny-Live Signature Gate Preview

## Intent

Consume the R249 local executable payload artifact and preview local signed request construction only.

## Non-Negotiables

- Do not write a signed request.
- Do not call Binance.
- Do not submit an order.
- Do not place an order or test order.
- Do not mutate env/config/lane controls/risk contracts.
- Do not disable the kill switch.
- Keep `signed_order_request_created=false`, `submit_allowed=false`, `order_placed=false`, `binance_call_allowed=false`, and `network_allowed=false`.

## Expected Inputs

- `logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson`
- Official lane `BTCUSDT|8m|short|ladder_close_50_618`

## Expected Output

A preview-only operator packet that explains what a future signature gate would require, while preserving no-write, no-network, no-submit, and no-order safety.
