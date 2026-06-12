# R253 Tiny-Live Final Read-Only Mark Price Refresh Gate

## Purpose

Perform a final public read-only Binance mark-price and exchangeInfo refresh before any future tiny-live submit gate.

## Scope

Official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

R253 should consume:

- R252 submit readiness preview
- R251E runtime-source signed request write gate
- R251 signed request artifact
- R249 executable payload artifact
- R248 stop/take-profit source
- R242 read-only precision/mark-price reference

## Required Behavior

- Fetch public Binance Futures read-only mark price.
- Fetch public Binance Futures exchangeInfo precision.
- Validate min notional.
- Validate quantity step rounding.
- Validate stop/take-profit direction against the fresh mark price.
- Compute notional after rounding.
- Compare fresh mark price against the signed artifact reference price.
- Decide whether the signed request must be regenerated before any submit gate.

## Forbidden

- No order endpoint.
- No test-order endpoint.
- No private endpoint.
- No account endpoint.
- No signing.
- No HMAC signature creation.
- No signed request writing.
- No submit.
- No order placement.
- No env/config/lane-control mutation.
- No kill switch disable.
- No secret reads or prints.

## Expected Outcome

R253 should produce a final read-only refresh packet and, only after exact confirmation, append its own read-only refresh ledger. It must not authorize submit. If fresh mark price/precision invalidates the existing signed request risk context, it must require signed request regeneration before any submit phase.
