# R259 Tiny-Live Fresh Cycle Checkpoint

R259 creates the fresh-cycle checkpoint packet for:

`BTCUSDT|8m|short|ladder_close_50_618`

This phase is checkpoint/orchestration only. It does not run the fresh cycle,
call Binance, call network endpoints, sign, regenerate signed requests, submit,
arm live controls, mutate configs, disable kill switches, or place orders. It
reads local R258/R257/R256/R255/R254/R253B/R253 artifacts plus read-only lane
and risk controls, then can append only its own R259 checkpoint ledger after the
exact confirmation phrase.

## Current Blockers

R258 preserved:

- `signed_request_timestamp_stale`
- `official_lane_not_tiny_live`
- `live_execution_not_enabled`

R259 therefore reports no-go for manual submit now and coordinates the required
fresh cycle:

1. R253 final readonly refresh.
2. R253B fresh signed request regeneration.
3. R254 submit gate preview.
4. R255 actual submit gate dry preview.
5. R258 manual checkpoint re-check.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint
```

Record checkpoint only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint \
  --record-fresh-cycle-checkpoint \
  --confirm-tiny-live-fresh-cycle-checkpoint "I CONFIRM TINY LIVE FRESH CYCLE CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Rejected recording proof:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint \
  --record-fresh-cycle-checkpoint \
  --confirm-tiny-live-fresh-cycle-checkpoint "wrong"
```

## Checkpoint Packet

R259 reports:

- whether R258/R257/R256/R255/R254/R253B/R253 are present.
- whether each fresh-cycle step is missing, stale, blocked, or ready.
- the deterministic next fresh-cycle step.
- the current R258 blockers.
- whether live controls still require manual arming review.
- exact command templates for R253, R253B, R254, R255, and R258 re-check.
- that all commands are templates only and must not be auto-run.
- what must not be run yet.
- the future R260 engineering move after fresh-cycle evidence is complete.

## Ledger

Confirmed R259 records append only:

`logs/hammer_radar_forward/tiny_live_fresh_cycle_checkpoint.ndjson`

Preview and bad-confirmation paths write no R259 ledger.

## Safety

R259 preserves:

- `fresh_cycle_checkpoint_only=true`
- `submit_allowed=false`
- `submit_attempted=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `binance_account_endpoint_called=false`
- `binance_exchange_info_endpoint_called=false`
- `binance_mark_price_endpoint_called=false`
- `private_binance_endpoint_called=false`
- `signed_binance_endpoint_called=false`
- `network_allowed=false`
- `hmac_signature_created=false`
- `signed_request_written=false`
- `live_controls_armed_by_phase=false`
- `secrets_read=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- no env/config/lane-control/risk-contract/live-control mutation

## Next Phase

R260 should be a manual live-submit execution checkpoint after fresh-cycle
evidence is complete. It must still not auto-submit. It should verify the fresh
signed request age in seconds, R255 dry-preview state, intentional operator
arming of live controls, duplicate-submit protection, and show the final manual
command for the operator to run outside the Codex task.
