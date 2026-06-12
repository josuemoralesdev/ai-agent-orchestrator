# R253 Tiny-Live Final Readonly Mark Price Refresh Gate

R253 adds the final public read-only Binance market refresh required after R252 and before any future submit-gate preview for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

This phase is not submit, not signing, and not order placement.

## Scope

R253 consumes the latest local artifacts from:

- R252 submit readiness preview
- R251E runtime-source signed request write gate
- R251 signed request write gate
- R249 executable payload write gate
- R248 stop/take-profit source gate
- R242 Binance read-only precision / mark-price gate

It can optionally call only these public Binance Futures endpoints after the exact confirmation phrase:

- `GET /fapi/v1/exchangeInfo`
- `GET /fapi/v1/premiumIndex?symbol=BTCUSDT`

It compares the fresh mark/precision context with the already-signed request context:

- signed quantity step validity
- notional at the fresh mark price
- min-notional compliance
- short stop direction
- short take-profit direction
- fresh-mark drift from the signed reference price
- estimated stop loss and take-profit reward from the fresh mark

## Command

Preview only, no network and no ledger write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-readonly-mark-price-refresh-gate
```

Fetch public read-only market context and append the R253 ledger only after exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-readonly-mark-price-refresh-gate \
  --fetch-final-readonly-market \
  --confirm-tiny-live-final-readonly-refresh "I CONFIRM TINY LIVE FINAL READONLY MARK PRICE REFRESH ONLY; NO SUBMIT; NO ORDER; NO PRIVATE BINANCE CALL."
```

Bad confirmation rejects without network and without ledger write.

## Artifact

Confirmed successful public read-only fetches append:

`logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson`

The ledger records fresh market context, signed artifact context, the compatibility comparison, the regeneration decision, the final refresh gate matrix, and safety flags.

## Safety

R253 must preserve:

- `submit_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- no order endpoint
- no test-order endpoint
- no account/private/signed Binance endpoint
- no HMAC signing
- no signed request write
- no secret read or secret output
- no env/config/lane-control mutation
- kill switch unchanged
- official tiny-live lane unchanged

## Status Outcomes

Top-level status:

- `TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_READY`
- `TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_REJECTED`
- `TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_FETCHED`
- `TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_BLOCKED`
- `TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_ERROR`

Overall status:

- `TINY_LIVE_FINAL_READONLY_REFRESH_READY_FOR_CONFIRMATION`
- `TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_REGENERATE_SIGNED_REQUEST_REQUIRED`
- `TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_READY_FOR_SUBMIT_GATE_PREVIEW`
- `TINY_LIVE_FINAL_READONLY_REFRESH_REJECTED_BAD_CONFIRMATION`
- `TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_ENDPOINT_SAFETY`
- `TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_SIGNED_ARTIFACT`
- `TINY_LIVE_FINAL_READONLY_REFRESH_BLOCKED_BY_MARKET_VALIDATION`
- `UNKNOWN_NEEDS_MANUAL_REVIEW`

## Next Phase

R254 should consume R253. If R253 says the fresh context is compatible, R254 previews the final submit gate only, keeps `submit_allowed=false`, does not call Binance order endpoints, does not submit, and prepares the exact future submit confirmation phrase for a separate final write/submit gate.
