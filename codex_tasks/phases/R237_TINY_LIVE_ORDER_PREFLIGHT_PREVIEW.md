# R237 Tiny Live Order Preflight Preview

## Intent

Consume the R236 tiny-live lane-arm write gate and preview the requirements for
a future order-preflight phase.

Official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

## Required Behavior

- Read latest `logs/hammer_radar_forward/tiny_live_lane_arm_write_gate.ndjson`.
- Require R236 lane-arm artifact status written and valid.
- Reconfirm R228 evidence, R230 risk contract config, R232 authorization,
  R234 execution-enable, and R235 lane-arm preview provenance.
- Re-read `configs/hammer_radar/lane_controls.json` as read-only context.
- Preview order-preflight prerequisites only.
- Keep `order_payload_created=false`.
- Keep `order_payload_allowed=false`.
- Keep `order_ready=false`.
- Keep `live_ready_today=false`.
- Keep `binance_call_allowed=false`.
- Keep `kill_switch_disabled=false`.

## Forbidden Behavior

- No Binance calls unless a separate future read-only connectivity gate exists
  and is explicitly safe for that phase.
- No order placement.
- No test order placement.
- No signed trading or signed order requests.
- No order payload creation unless separately gated later.
- No executable payload files.
- No live connector submission.
- No kill-switch disable.
- No env writes.
- No risk-contract config writes.
- No lane-control writes.
- No transfer or withdraw calls.

## Expected Output

R237 should produce:

- input summary over R236/R235/R234/R232/R230/R228
- order-preflight requirement preview
- validation matrix
- operator review packet
- explicit non-actions
- recommended next engineering move for a separately gated order-preflight write
  or payload-preview phase
- safety object proving no order, payload, Binance/network, env/config, or
  kill-switch mutation occurred
