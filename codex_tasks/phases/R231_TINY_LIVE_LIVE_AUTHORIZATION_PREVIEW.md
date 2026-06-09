# R231 Tiny-Live Live Authorization Preview

## Phase

R231 Tiny-Live Live Authorization Preview

## Purpose

Consume the R230 written risk-contract config for the official lane and preview the remaining live authorization requirements. This phase is a preview/audit phase only.

Official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Required Inputs

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson`
- latest R229/R230 status as local evidence

## Must Do

- Confirm the R230 risk-contract config exists for the official lane.
- Confirm the written contract remains `CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED`.
- Confirm `live_authorized=false`.
- Confirm `live_execution_enabled=false`.
- Preview the human/operator evidence still required before any future live authorization.
- Produce an operator review packet and recommended next engineering move.

## Must Not Do

- No live execution.
- No Binance/network calls.
- No order placement.
- No test order placement.
- No signed trading request.
- No executable payload.
- No order payload.
- No lane arming.
- No kill switch disable.
- No env write.
- No config write unless a future phase explicitly allows it.
- No lane controls write.
- No transfer or withdraw.
- No strategy promotion.
- No betrayal promotion.

## Expected Safety Defaults

- `live_authorization_created=false`
- `live_execution_enabled=false`
- `order_payload_created=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `network_allowed=false`
- `lane_promoted=false`
- `official_tiny_live_lane_changed=false`
- `kill_switch_disabled=false`
- `paper_live_separation_intact=true`

## Recommended Command Shape

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-live-authorization-preview
```
