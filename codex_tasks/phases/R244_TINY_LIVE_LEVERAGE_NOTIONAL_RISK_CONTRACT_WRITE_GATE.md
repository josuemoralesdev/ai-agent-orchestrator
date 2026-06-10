# R244 Tiny-Live Leverage / Notional Risk Contract Write Gate

## Objective

Consume the R243 tiny-live leverage / notional adjustment preview and create a guarded write gate for updating only the official-lane risk contract config/artifact.

Official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Required Behavior

- Read the latest R243 adjustment preview.
- Require the preview to show the reviewed 44 USDT margin budget, 10x leverage, and 440 USDT max notional model.
- Require the adjusted quantity preview to clear BTCUSDT step size and min-notional checks.
- Require an exact operator confirmation phrase before writing.
- Write only the risk-contract config/artifact needed for the adjusted model.
- Preserve max-loss review semantics; do not silently increase max loss.
- Emit explicit post-write verification.

## Non-Actions

- No Binance/network calls.
- No executable payload creation.
- No signed request.
- No order or test order.
- No env writes.
- No lane controls write.
- No live execution enablement.
- No kill switch disable.
- No official lane change.

## Confirmation Phrase Draft

`I CONFIRM TINY LIVE LEVERAGE NOTIONAL RISK CONTRACT WRITE GATE ONLY; WRITE RISK CONFIG ONLY; NO ORDER; NO BINANCE CALL.`
