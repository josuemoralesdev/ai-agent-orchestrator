# R236 Tiny Live Lane Arm Write Gate

## Intent

Consume the R235 tiny-live lane arm preview and create a guarded write gate for
future official-lane arming:

`BTCUSDT|8m|short|ladder_close_50_618`

This future phase may preview a lane-arm write and, only after an exact operator
confirmation phrase, perform the bounded lane-arm mutation defined by that
phase. It must not place orders, call Binance/network, create order payloads,
disable the kill switch, or bypass human approval.

## Required Behavior

- Read latest `logs/hammer_radar_forward/tiny_live_lane_arm_preview.ndjson`.
- Require R235 preview status ready for future gate.
- Reconfirm R228 evidence, R230 risk contract config, R232 authorization, and R234 execution-enable artifacts.
- Re-read `configs/hammer_radar/lane_controls.json` before any write preview.
- Require an exact operator confirmation phrase before any bounded lane-arm write.
- Preserve `order_payload_created=false`.
- Preserve `order_ready=false`.
- Preserve `binance_call_allowed=false`.
- Preserve `kill_switch_disabled=false`.
- Append an audit record for preview/reject/write outcomes.

## Forbidden Behavior

- No Binance calls.
- No network calls.
- No order placement or test orders.
- No signed trading or order requests.
- No executable order payloads.
- No order payload files.
- No kill switch disable unless separately guarded and confirmed in a later phase.
- No live connector submission.
- No transfer or withdraw calls.
- No env write.
- No risk contract config write.

## Expected CLI

```text
tiny-live-lane-arm-write-gate
```

Expected args:

- `--write-lane-arm`
- `--confirm-tiny-live-lane-arm-write <phrase>`

## Safety Notes

R236 is a lane-arm write gate only. It is not order preflight, not Binance
connectivity, not order payload creation, and not live connector submission.
