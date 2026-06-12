# R252 Tiny-Live Submit Readiness Preview

## Intent

Consume the latest R251/R251C signed request artifact plus R251D runtime credential source readiness and preview whether a future submit gate could be prepared for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Scope

R252 is preview only. It must inspect local artifacts and produce a submit-readiness packet without calling Binance, submitting, placing orders, creating executable submit payloads, mutating env/config/lane controls, changing live flags, or disabling the kill switch.

## Required Inputs

- Latest R251 signed request artifact in `logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson`.
- Latest R251C wrapper drill record in `logs/hammer_radar_forward/tiny_live_signed_request_with_credentials_drill.ndjson`.
- Latest R251D runtime credential source drill record in `logs/hammer_radar_forward/tiny_live_runtime_credential_source_drill.ndjson`.
- Official lane remains `BTCUSDT|8m|short|ladder_close_50_618`.

## Required Preview Checks

- Three signed requests exist: main, stop, and take-profit.
- Each signature is 64 lowercase hex chars.
- `submit_allowed=false`.
- `network_allowed=false`.
- `binance_call_allowed=false`.
- `order_placed=false`.
- Raw API key and raw API secret are absent from artifacts.
- Runtime credential source readiness exists for future signing/submission drill reuse, without printing or persisting credential values.
- A future read-only mark-price refresh is required before any submit gate.
- A future final human submit confirmation is required.

## Non-Actions

- No Binance calls.
- No network calls.
- No submit.
- No order placement.
- No test order placement.
- No account, exchange-info, mark-price, transfer, or withdraw endpoint calls.
- No env/config/lane-control writes.
- No kill-switch disable.
- No strategy promotion.

## Expected Output Direction

The R252 packet should recommend either:

- `REVIEW_SIGNED_REQUEST_AND_REFRESH_MARK_PRICE_BEFORE_SUBMIT_GATE`, or
- `FIX_SIGNED_REQUEST_ARTIFACT_BLOCKER`.

It must not recommend submitting or placing an order from R252.
