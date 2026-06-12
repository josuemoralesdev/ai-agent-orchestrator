# R255 Tiny-Live Actual Submit Gate

## Objective

Implement the first actual tiny-live submit gate for:

`BTCUSDT|8m|short|ladder_close_50_618`

R255 is the first phase that may submit live Binance Futures orders, but only after every gate below passes and the operator provides the exact R255 confirmation phrase produced by R254.

## Required Inputs

- latest recorded R254 submit gate preview
- latest R253B fresh-context signed request artifact
- latest R253B executable payload artifact
- latest R253B stop/take-profit source artifact
- latest R253 final read-only market context
- current runtime credential source readiness
- current kill-switch and lane-control state

## Mandatory Enforcement

R255 must verify before submit:

- latest R254 preview is recorded and valid
- latest R253B signed request is still the latest signed request
- signed request age is within the allowed submit window
- request timestamps are fresh enough or regenerated under an explicit regeneration gate
- runtime credential source is ready without printing or persisting secrets
- kill switch state allows tiny live
- order endpoint allowlist is exactly `POST /fapi/v1/order`
- exactly three orders are intended
- order sequence is main market, then stop, then take-profit
- idempotency/dedupe proves no prior live order for the same signal
- max loss and notional remain within the tiny-live risk contract
- current mark price is checked before submit
- post-submit reconciliation plan exists
- exact operator R255 confirmation is present

## Order Semantics

If all gates pass, R255 may place exactly three Binance Futures orders:

- main `SELL MARKET 0.007 BTC`
- stop `BUY STOP_MARKET reduceOnly=true`
- take-profit `BUY TAKE_PROFIT_MARKET reduceOnly=true`

R255 must never place extra orders.

## Required Records

R255 must record:

- pre-submit gate decision
- idempotency/dedupe key
- endpoint allowlist result
- order submission attempts
- sanitized Binance responses
- post-submit reconciliation state
- abort/reconcile instructions

## Abort Conditions

Abort before any submit if:

- R254 preview is missing or invalid
- R253B signed request is missing, stale, superseded, or malformed
- confirmation phrase is absent or not exact
- kill switch blocks tiny live
- endpoint allowlist differs from `POST /fapi/v1/order`
- intended order count is not exactly three
- idempotency detects prior live order
- balance, margin, mark price, notional, or risk checks fail
- post-submit reconciliation cannot be recorded

## Non-Negotiables

- no extra orders
- no transfer or withdraw endpoints
- no account setting changes
- no secret printing or persistence
- no env/config/lane-control mutation unless a future phase explicitly requires it
- no bypass of kill switch, idempotency, dedupe, endpoint allowlist, or operator confirmation
