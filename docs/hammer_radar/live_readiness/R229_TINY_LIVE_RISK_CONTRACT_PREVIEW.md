# R229 Tiny Live Risk Contract Preview

R229 consumes the latest recorded R228 ready packet for the official protected lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It produces a deterministic risk-contract preview for operator review only. It does not write `configs/hammer_radar/tiny_live_risk_contracts.json`, change lane controls, enable live execution, create order payloads, call Binance/network, or place orders.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-preview
```

Record the preview ledger only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-preview \
  --record-risk-preview \
  --confirm-tiny-live-risk-contract-preview "I CONFIRM TINY LIVE RISK CONTRACT PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract-preview \
  --record-risk-preview \
  --confirm-tiny-live-risk-contract-preview "wrong"
```

## Inputs

R229 reads local surfaces only:

- `logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson`
- read-only `configs/hammer_radar/tiny_live_risk_contracts.json`

The append-only R229 ledger is:

```text
logs/hammer_radar_forward/tiny_live_risk_contract_preview.ndjson
```

## Preview Rules

The preview is ready only when the latest R228 packet:

- exists
- has status `TINY_LIVE_10_OF_10_READY_PACKET_READY` or `TINY_LIVE_10_OF_10_READY_PACKET_RECORDED`
- still targets `BTCUSDT|8m|short|ladder_close_50_618`
- has `evidence_ready=true`
- has `fisherman_ready=true`
- has `operator_review_ready=true`
- keeps `risk_contract_ready=false`
- keeps `live_authorization_ready=false`
- keeps `order_ready=false`

## Preview Defaults

If no approved official-lane risk contract exists, R229 uses conservative preview-only defaults:

- `capital_mode=tiny_live_preview`
- `proposed_tiny_live_margin_usdt=44`
- `proposed_leverage=1`
- `proposed_max_notional_usdt=44`
- `proposed_max_loss_usdt=4.44`
- stop required
- take profit required
- kill switch required
- operator final approval required
- later config write required
- later live authorization required

These values are not approval. They are not written to config.

## Safety

R229 keeps:

- `risk_contract_config_written=false`
- `risk_contract_approved=false`
- `live_authorization_ready=false`
- `live_execution_ready=false`
- `order_ready=false`
- `live_ready_today=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `network_allowed=false`
- `config_written=false`
- `lane_config_written=false`
- `global_live_flags_changed=false`
- `kill_switch_disabled=false`
- `betrayal_promoted=false`
- `official_tiny_live_lane_changed=false`

## Follow-Up

R230 should consume the recorded R229 preview and implement a guarded config-write gate. R230 must still avoid live execution, Binance/network calls, order placement, lane arming, kill-switch disablement, and any config mutation except the explicitly confirmed bounded risk-contract config write.
