# R236 Tiny Live Lane Arm Write Gate

R236 consumes the official tiny-live lane path:

`BTCUSDT|8m|short|ladder_close_50_618`

It moves R235 from preview to an exact-confirmation lane-arm write gate. The
implemented mutation is ledger-only: R236 appends a bounded local lane-arm
artifact to `logs/hammer_radar_forward/tiny_live_lane_arm_write_gate.ndjson`
only when the exact R236 phrase is supplied.

R236 does not mutate `configs/hammer_radar/lane_controls.json`. The existing
lane-control schema includes lane modes, but this phase keeps lane config
read-only because order paths must remain non-executable and the preferred safe
default is ledger-only.

## Commands

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-arm-write-gate
```

Rejected confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-arm-write-gate \
  --write-lane-arm \
  --confirm-tiny-live-lane-arm-write "wrong"
```

Write the lane-arm artifact only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-arm-write-gate \
  --write-lane-arm \
  --confirm-tiny-live-lane-arm-write "I CONFIRM TINY LIVE LANE ARM WRITE ONLY; NO ORDER; NO BINANCE CALL; KEEP KILL SWITCH ACTIVE."
```

## Inputs

R236 reads local surfaces only:

- `logs/hammer_radar_forward/tiny_live_lane_arm_preview.ndjson`
- `logs/hammer_radar_forward/tiny_live_live_execution_enable_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_live_authorization_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_risk_contract_config_write_gate.ndjson`
- `logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson`
- read-only `configs/hammer_radar/tiny_live_risk_contracts.json`
- read-only `configs/hammer_radar/lane_controls.json`

## Write Rules

The write gate is ready only when:

- latest R235 preview is ready for a future lane-arm gate
- latest R234 execution-enable artifact exists and validates
- latest R232 authorization artifact exists and validates
- matching R230 official-lane risk contract config exists and validates
- R228 evidence and fisherman readiness are true
- official lane is `BTCUSDT|8m|short|ladder_close_50_618`
- lane controls exist and show the official lane is not already armed
- proposed lane-arm object validates
- exact R236 confirmation is supplied for the write path

## Safety

R236 keeps:

- `order_payload_created=false`
- `order_payload_allowed=false`
- `executable_payload_created=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_call_allowed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `network_allowed=false`
- `kill_switch_disabled=false`
- `env_mutated=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_controls_written=false`
- `paper_outcomes_appended=false`
- `strategy_performance_appended=false`
- `strategy_promotion_status_appended=false`

When exactly confirmed, the R236 ledger artifact can show
`lane_armed=true`, but it is still not order authority. R237 must separately
preview order-preflight requirements without order payload creation, Binance
calls, or order placement.
