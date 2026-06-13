# R257 Tiny-Live Final Pre-Submit Arming Drill

R257 creates the final manual decision packet before any operator-considered
real submit for:

`BTCUSDT|8m|short|ladder_close_50_618`

This phase does not submit, call Binance, call order endpoints, sign,
regenerate signed requests, mutate live controls, arm controls, or place
orders. It reads local R256/R255/R254/R253B artifacts plus local lane/risk
controls and can append only its own R257 drill ledger after exact confirmation.

## Current Blockers

The latest R256/R255 path currently reports:

- `signed_request_timestamp_stale`
- `official_lane_not_tiny_live`
- `live_execution_not_enabled`

The expected manual packet keeps `operator_should_submit_now=false` and points
the operator to regenerate first while live controls remain intentionally off.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill
```

Record drill only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill \
  --record-final-pre-submit-arming-drill \
  --confirm-tiny-live-final-pre-submit-arming-drill "I CONFIRM TINY LIVE FINAL PRE-SUBMIT ARMING DRILL RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Rejected recording proof:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill \
  --record-final-pre-submit-arming-drill \
  --confirm-tiny-live-final-pre-submit-arming-drill "wrong"
```

## Drill Checks

R257 confirms:

- R256 operator runbook is available and reviewed.
- R255 actual submit gate dry preview exists.
- R254 submit gate preview exists.
- R253B regeneration artifact exists.
- signed request regeneration is required when timestamp is stale.
- live controls still require manual arming when lane mode or live execution is off.
- the exact R255 real-submit command template exists but must not be run automatically.
- post-submit reconciliation, partial-success handling, abort cleanup, and duplicate-submit protection exist.

## Ledger

Confirmed R257 records append only:

`logs/hammer_radar_forward/tiny_live_final_pre_submit_arming_drill.ndjson`

Preview and bad-confirmation paths write no R257 ledger.

## Safety

R257 preserves:

- `final_pre_submit_arming_drill_only=true`
- `submit_allowed=false`
- `submit_attempted=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `network_allowed=false`
- `hmac_signature_created=false`
- `signed_request_written=false`
- `live_controls_armed_by_phase=false`
- `secrets_read=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- no env/config/lane-control/risk-contract/live-control mutation

## Next Phase

R258 should be the manual-submit checkpoint immediately before any user-run real
submit command. It must still not auto-submit.
