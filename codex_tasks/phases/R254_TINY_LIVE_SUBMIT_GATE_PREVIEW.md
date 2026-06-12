# R254 Tiny-Live Submit Gate Preview

## Phase Intent

Consume the latest R253 final read-only refresh result and preview the final tiny-live submit gate only.

R254 is not submit, not order placement, and not a signed request write.

## Required Inputs

- Latest R253 final read-only mark-price refresh gate record
- Latest R252 submit readiness preview
- Latest R251E runtime-source signed request artifact
- Latest R251 signed request artifact
- Latest R249 executable payload artifact
- Latest R248 stop/take-profit source artifact

## Required Behavior

- If R253 says fresh market context is compatible with the signed artifact, preview the final submit-gate requirements.
- If R253 says the signed request must be regenerated, block and instruct the operator to regenerate before submit preview.
- Keep `submit_allowed=false`.
- Keep `order_placed=false`.
- Do not call Binance order endpoints.
- Do not call Binance test-order endpoints.
- Do not call Binance private/account/signed endpoints.
- Do not submit.
- Do not place orders.
- Do not sign.
- Do not write signed requests.
- Do not read or print secrets.
- Do not mutate env/config/lane controls.
- Do not disable the kill switch.
- Preserve the official lane: `BTCUSDT|8m|short|ladder_close_50_618`.

## Output

The preview should include:

- R253 compatibility summary
- signed artifact submit-control summary
- final submit-gate blocker matrix
- exact future submit confirmation phrase for a separate final write/submit gate
- explicit non-actions:
  - do not place order
  - do not submit from R254
  - do not call Binance order endpoint from R254

## Safety

R254 must report:

- `submit_allowed=false`
- `submit_attempted=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `binance_account_endpoint_called=false`
- `private_binance_endpoint_called=false`
- `signed_binance_endpoint_called=false`
- `network_allowed=false`
- `hmac_signature_created=false`
- `signed_request_written=false`
- `secrets_read=false`
- `secrets_shown=false`
- `secret_values_in_output=false`
- `paper_live_separation_intact=true`
- `official_tiny_live_lane_changed=false`

## Validation

Add focused tests for:

- CLI exists and returns JSON
- R253 compatible path allows submit-gate preview only
- R253 regenerate-required path blocks
- missing R253 blocks
- no network calls
- no order/test-order/account/private/signed endpoints
- no signing
- no submit
- no order placement
- no env/config/lane-control mutation
- no secret values in output
