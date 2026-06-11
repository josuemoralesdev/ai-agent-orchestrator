# R251 Tiny-Live Signed Request Write Gate

## Intent

Consume the recorded R250 signature gate preview and create a local signed request artifact only under an exact R251 confirmation phrase.

## Required Inputs

- Latest R250 `tiny_live_signature_gate_preview.ndjson` record for `BTCUSDT|8m|short|ladder_close_50_618`
- Latest R249 executable payload artifact
- A safe secret access strategy that does not print or commit secrets

## Non-Negotiables

- No Binance calls.
- No network calls.
- No submit.
- No test order.
- No order placement.
- No env/config/lane-control mutation.
- No kill-switch disable.
- No secrets printed.
- No signed request artifact unless exact R251 confirmation is provided.

## Expected Output

- Preview by default.
- Confirmed mutation limited to a local R251 signed request write-gate ledger.
- Signed request artifact remains `submit_allowed=false`, `binance_call_allowed=false`, `network_allowed=false`, and `order_placed=false`.
- R252 or later must handle any submit preview/write gate separately.
