# R245 Tiny-Live Order Payload Refresh Preview

## Objective

Consume the R244 adjusted tiny-live risk contract and refresh the non-executable order payload preview for:

`BTCUSDT|8m|short|ladder_close_50_618`

The refreshed preview must use:

- `margin_budget_usdt=44`
- `leverage=10`
- `max_notional_usdt=440`
- `max_position_notional_usdt=440`

## Inputs

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `logs/hammer_radar_forward/tiny_live_leverage_notional_risk_contract_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson`
- existing R240/R239 order payload preview/write-gate patterns

## Required Behavior

- Preview refreshed non-executable payload shape only.
- Use the R244 adjusted risk contract as the risk source.
- Use latest recorded R242 precision/mark-price evidence for quantity rounding preview.
- Preserve official lane identity.
- Preserve kill-switch and operator final approval requirements.
- Keep live authorization false and live execution disabled.

## Forbidden

- No executable payload.
- No submit-ready payload.
- No signed request.
- No signed order request.
- No signed trading request.
- No Binance order endpoint.
- No Binance test-order endpoint.
- No private/account endpoint.
- No network call.
- No order placement.
- No env mutation.
- No lane-control mutation.
- No kill switch disable.

## Expected Next Status

R245 should produce a preview-only result that can feed a later guarded write gate if the refreshed non-executable payload validates under the R244 10x model.
