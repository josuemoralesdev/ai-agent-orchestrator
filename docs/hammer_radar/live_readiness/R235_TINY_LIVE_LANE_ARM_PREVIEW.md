# R235 Tiny Live Lane Arm Preview

R235 consumes the current official tiny-live lane path:

`BTCUSDT|8m|short|ladder_close_50_618`

It previews future lane-arm requirements after the R234 live execution enable
artifact. It does not arm the lane, create order payloads, call
Binance/network, place orders, disable the kill switch, mutate env/config/lane
state, or create executable payloads.

## Commands

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-arm-preview
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-arm-preview \
  --record-lane-arm-preview \
  --confirm-tiny-live-lane-arm-preview "wrong"
```

Record the preview ledger only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-arm-preview \
  --record-lane-arm-preview \
  --confirm-tiny-live-lane-arm-preview "I CONFIRM TINY LIVE LANE ARM PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Inputs

R235 reads local surfaces only:

- `logs/hammer_radar_forward/tiny_live_live_execution_enable_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_live_execution_enable_preview.ndjson`
- `logs/hammer_radar_forward/tiny_live_live_authorization_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson`
- read-only `configs/hammer_radar/tiny_live_risk_contracts.json`
- read-only `configs/hammer_radar/lane_controls.json`

The append-only R235 preview ledger is:

```text
logs/hammer_radar_forward/tiny_live_lane_arm_preview.ndjson
```

## Preview Rules

The preview is ready only when:

- latest R228 packet exists with `evidence_ready=true`
- latest R228 packet has `fisherman_ready=true`
- latest R230 risk contract config write gate exists or the matching config entry exists
- matching official-lane risk contract exists and validates
- latest R232 authorization artifact exists and validates
- latest R234 execution-enable artifact exists and validates
- R232/R234 show `live_authorized=true`
- R234 shows `live_execution_enabled=true`
- `lane_armed=false`
- `order_payload_allowed=false`
- `binance_call_allowed=false`
- read-only lane controls show the official lane is not already armed

## Output

R235 reports:

- `input_summary`
- `authorization_summary`
- `execution_enable_summary`
- `lane_controls_readonly_summary`
- `lane_arm_requirement_preview`
- `lane_arm_gate_matrix`
- `operator_lane_arm_review_packet`
- next operator and engineering recommendations
- explicit `do_not_run_yet`
- safety flags proving no env/config/network/order/promotion behavior

The only accepted recording phrase is:

`I CONFIRM TINY LIVE LANE ARM PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL.`

## Safety

R235 keeps:

- `lane_arm_written=false`
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
- `kill_switch_disabled=false`
- `official_tiny_live_lane_changed=false`

When exactly confirmed, only `logs/hammer_radar_forward/tiny_live_lane_arm_preview.ndjson`
is appended. That record is not lane arming and is not order authority.

## Follow-Up

R236 should create a guarded Tiny-Live Lane Arm Write Gate that consumes R235.
It must still avoid Binance/network calls, order placement, order payload
creation, and kill-switch disablement.
