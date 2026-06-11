# R248 Tiny-Live Stop / Take-Profit Source Gate

## Purpose

Establish the final stop and take-profit source for the official tiny-live payload:

`BTCUSDT|8m|short|ladder_close_50_618`

R248 should consume the R247 executable payload preview and provide a guarded path to preview or record final protective levels only after exact confirmation.

## Required Inputs

- Latest R247 executable payload preview.
- Latest R246 refreshed non-executable payload artifact.
- Latest R245 payload refresh preview.
- Latest R244 adjusted risk contract.
- Latest R242 read-only precision/mark-price result.
- Latest R238 order preflight.
- Latest R236 lane arm.
- Latest R228 evidence packet.

## Required Safety

- No executable payload unless final stop/take-profit levels are valid and a later phase explicitly authorizes that write gate.
- No signed request.
- No signed trading request.
- No Binance/network call.
- No order placement.
- No test order placement.
- No env mutation.
- No config mutation.
- No lane-controls mutation.
- No risk-contract config mutation.
- No kill-switch disable.
- No live connector submission.
- No official lane change.
- No secrets printed.

## Expected Behavior

- Identify the approved local source for final stop and take-profit levels.
- Validate both levels against BTCUSDT price precision from R242.
- Validate protective order direction for a short position:
  - stop side `BUY`, reduce-only
  - take-profit side `BUY`, reduce-only
- Preview levels by default.
- Optionally record only the stop/take-profit source packet after an exact future R248 confirmation phrase.
- Keep executable payload creation blocked when either level is absent or invalid.

## Non-Actions

- Do not create an executable order payload.
- Do not create a signed order request.
- Do not call Binance.
- Do not place an order.
- Do not disable the kill switch.
