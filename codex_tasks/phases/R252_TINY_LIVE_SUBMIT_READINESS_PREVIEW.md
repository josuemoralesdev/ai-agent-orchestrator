# R252 Tiny-Live Submit Readiness Preview

## Intent

Consume the R251 signed request artifact and preview whether the official tiny-live lane has enough local evidence for a future submit gate.

## Required Inputs

- Latest `logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson`
- Latest R251 signed request artifact for `BTCUSDT|8m|short|ladder_close_50_618`
- Latest R250 signature gate preview
- Latest R249 executable payload artifact
- A future read-only mark-price refresh before any submit gate

## Non-Negotiables

- No Binance call.
- No network call.
- No submit.
- No order placement.
- No test order.
- No private endpoint call.
- No API key or secret printing.
- No env/config/lane-control mutation.
- No kill switch disable.
- Keep `submit_allowed=false`.
- Keep `order_placed=false`.
- Keep `real_order_placed=false`.
- Keep `execution_attempted=false`.

## Expected Output

Implement a preview-only operator surface that reports:

- R251 signed request artifact found/valid
- all three signed requests present
- signatures are 64-character hex strings
- submit remains blocked pending a future explicit submit gate
- read-only mark-price refresh is required before submit
- operator must not submit now
- engineering next move remains a controlled submit gate only after read-only refresh evidence

## Suggested Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-submit-readiness-preview
```
