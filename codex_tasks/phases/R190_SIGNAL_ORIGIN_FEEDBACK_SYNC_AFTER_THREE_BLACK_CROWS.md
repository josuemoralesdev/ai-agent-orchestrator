# R190 Signal Origin Feedback Sync After Three Black Crows

## Purpose

Sync R189 Three Black Crows local detector evidence back into signal-origin
review surfaces without promoting origins, lanes, configs, or live execution.

## Scope

- Read `logs/hammer_radar_forward/three_black_crows_local_detections.ndjson`.
- Read `logs/hammer_radar_forward/three_black_crows_paper_tags.ndjson`.
- Compose review-only feedback for:
  - `signal_origin_registry.ndjson`
  - `keter_signal_origin_scoring.ndjson`
  - `signal_origin_lane_matrix.ndjson`
- Recommend `three_black_crows` availability as
  `DETECTOR_AVAILABLE_AFTER_REVIEW` through review evidence only.

## Non-Negotiables

- No config writes.
- No env writes or env mutation.
- No Binance calls.
- No network calls.
- No orders or test orders.
- No order payloads or executable payloads.
- No signed requests.
- No lane mode changes.
- No tiny-live arming.
- No signal-origin promotion.
- No lane promotion.
- No live authorization.

## Expected Output

R190 should produce an append-only review packet showing:

- latest R189 detection count
- latest R189 paper tag count
- target lane `BTCUSDT|8m|short|ladder_close_50_618`
- signal origin `three_black_crows`
- previous registry availability `REGISTRY_ONLY`
- recommended future registry status `DETECTOR_AVAILABLE_AFTER_REVIEW`
- `still_paper_only=true`
- `ready_for_live=false`
- safety flags proving no config/network/order/live action occurred
