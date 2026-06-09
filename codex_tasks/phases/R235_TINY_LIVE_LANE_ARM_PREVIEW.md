# R235 Tiny-Live Lane Arm Preview

## Intent

Consume the R234 tiny-live live execution enable write gate and preview the
requirements for a later lane-arm gate for:

`BTCUSDT|8m|short|ladder_close_50_618`

This is preview-only. It must not arm the lane, place orders, call
Binance/network, create order payloads, disable the kill switch, mutate env, or
mutate configs.

## Required Behavior

- Read latest `logs/hammer_radar_forward/tiny_live_live_execution_enable_write_gate.ndjson`.
- Confirm the R234 execution-enable artifact exists and validates.
- Confirm `live_authorized=true`.
- Confirm `live_execution_enabled=true` only in the bounded R234 artifact.
- Confirm `lane_armed=false`.
- Confirm `order_payload_allowed=false`.
- Confirm `binance_call_allowed=false`.
- Confirm kill switch remains required.
- Preview lane-arm requirements only.
- Recommend the next guarded lane-arm write gate only after operator review.

## Forbidden Behavior

- No Binance calls.
- No network calls.
- No order placement or test orders.
- No signed trading or order requests.
- No executable order payloads.
- No lane controls write.
- No env write.
- No kill switch disable.
- No live connector submission.
- No transfer or withdraw calls.

## Expected Output

The CLI should produce a preview packet with:

- R234 artifact summary
- lane-arm readiness matrix
- explicit blockers
- operator review packet
- `do_not_run_yet`
- safety flags proving no mutation and no live action

## Recommended CLI Name

```text
tiny-live-lane-arm-preview
```
