# R231 Tiny Live Live Authorization Preview

R231 consumes the current official tiny-live lane path:

`BTCUSDT|8m|short|ladder_close_50_618`

It previews future live authorization requirements only. It does not create a live authorization object, enable live execution, arm the lane, create order payloads, call Binance/network, place orders, disable the kill switch, or mutate env/config/lane state.

## Commands

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-live-authorization-preview
```

Record the preview ledger only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-live-authorization-preview \
  --record-authorization-preview \
  --confirm-tiny-live-live-authorization-preview "I CONFIRM TINY LIVE LIVE AUTHORIZATION PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-live-authorization-preview \
  --record-authorization-preview \
  --confirm-tiny-live-live-authorization-preview "wrong"
```

## Inputs

R231 reads local surfaces only:

- `logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson`
- `logs/hammer_radar_forward/tiny_live_risk_contract_preview.ndjson`
- `logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson`
- read-only `configs/hammer_radar/tiny_live_risk_contracts.json`
- read-only `configs/hammer_radar/lane_controls.json`

The append-only R231 ledger is:

```text
logs/hammer_radar_forward/tiny_live_live_authorization_preview.ndjson
```

## Preview Rules

The preview is ready only when:

- latest R228 packet exists and has `evidence_ready=true`
- latest R228 packet has `fisherman_ready=true`
- latest R229 risk preview exists and has `risk_contract_preview_ready=true`
- latest R230 config write gate exists or the config entry exists
- matching official-lane risk contract exists in `configs/hammer_radar/tiny_live_risk_contracts.json`
- matching risk contract validates
- `approval_status=CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED`
- `live_authorized=false`
- `live_execution_enabled=false`
- `approved=false`
- order payloads and Binance calls remain forbidden until a later live gate
- official lane remains unchanged
- lane controls do not arm the 8m short lane
- kill switch is not disabled

## Output

R231 reports:

- `input_summary`
- `risk_contract_summary`
- `live_authorization_requirement_preview`
- `live_authorization_gate_matrix`
- `operator_live_authorization_review_packet`
- next operator and engineering recommendations
- explicit `do_not_run_yet`
- safety flags proving no live/config/network/order/promotion behavior

The future suggested authorization phrase is preview text only:

`I CONFIRM TINY LIVE AUTHORIZATION ONLY; NO ORDER; NO BINANCE CALL.`

That phrase is not accepted by R231 and does not authorize live execution.

## Safety

R231 keeps:

- `live_authorization_written=false`
- `live_authorization_created=false`
- `live_execution_enabled=false`
- `lane_armed=false`
- `order_ready=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `network_allowed=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_controls_written=false`
- `env_mutated=false`
- `global_live_flags_changed=false`
- `kill_switch_disabled=false`
- `official_tiny_live_lane_changed=false`

Only a correctly confirmed R231 recording appends the R231 preview ledger. It does not mutate configs or authorize live.

## Follow-Up

R232 may create a guarded live authorization write gate that consumes R231. R232 must still avoid live execution, Binance/network calls, order placement, order payload creation, and lane arming unless a later separately gated phase explicitly allows them.
