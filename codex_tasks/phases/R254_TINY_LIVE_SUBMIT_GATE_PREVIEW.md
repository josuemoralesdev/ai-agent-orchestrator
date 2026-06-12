# R254 Tiny-Live Submit Gate Preview

## Intent

Consume the R253B fresh-context regenerated signed request and the R253 final read-only refresh, then preview the final submit gate only.

R254 must not submit, place orders, call Binance order/test-order/private/account/signed endpoints, mutate env/config/lane controls, disable the kill switch, or set `submit_allowed=true`.

## Inputs

- `logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_final_readonly_mark_price_refresh_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json` read-only
- `configs/hammer_radar/lane_controls.json` read-only

## Required Conditions

- Latest R253B exists and is written.
- Latest R253B signed request artifact has three signed requests.
- All signatures are 64 hex characters.
- R253B secret validation passed.
- R253 final read-only refresh exists.
- R253 required signed request regeneration.
- R253B regenerated reference context matches the latest recorded R253 fresh mark context.
- `submit_allowed=false`.
- `order_placed=false`.
- `binance_order_endpoint_called=false`.
- `network_allowed=false`.

## Output

R254 should output a preview packet with:

- regenerated signed request readiness
- R253/R253B context reconciliation
- final submit blockers
- exact future submit confirmation phrase for a later separate final submit/write gate
- explicit non-actions:
  - do not submit
  - do not place order
  - do not call Binance order endpoint
  - do not disable kill switch

## Safety

Preserve:

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
- `secrets_shown=false`
- `secrets_persisted=false`
- `secret_values_in_output=false`
- `paper_live_separation_intact=true`

## Non-Goal

R254 is not a submit phase. It must only preview the final submit gate and prepare a future exact confirmation phrase for a later bounded submit/write phase.
