# R263 Tiny-Live Final Console, Lane Intelligence, And Controls Arming

R263 adds the final local operator console for:

`BTCUSDT|8m|short|ladder_close_50_618`

It composes the latest R262B contract-fit record, signed triplet previews,
R261 controls state, strategy promotion context, readiness state, and
lane/fisherman intelligence into one JSON/API/UI surface.

R263 is not a submit phase. Actual submit is deferred to R264.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console
```

Record final console review only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  --record-final-console-review \
  --confirm-final-console-review "I CONFIRM TINY LIVE FINAL CONSOLE REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Arm controls from final console only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-console \
  --arm-controls-from-final-console \
  --confirm-final-console-controls-arming "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT EXPERIMENTAL LANE ONLY; I ACCEPT 8M SHORT IS PAPER-ONLY/PROMOTION-MISMATCHED; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R263 final console accepted contract-fit 8m short experimental lane; preparing for R264 actual submit checkpoint."
```

## API And UI

- `GET /tiny-live/final-console`
- `POST /tiny-live/final-console/review/record`
- `POST /tiny-live/final-console/controls/arm`

The dashboard contains a Tiny Live Final Console card with contract-fit,
signed triplet, controls, lane/fisherman, promoted lane, readiness blocker,
and go/no-go panels. It contains no actual submit button.

## Lane Intelligence

The official R263 execution lane is still the 8m short lane. It is not one of
the promotion-ready tiny-live lanes by default.

Promotion-ready lanes displayed by the console:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

The console records experimental-lane acceptance only when the exact R263
arming phrase is supplied. This does not imply fisherman promotion and does
not switch the lane automatically.

## Mutation Boundary

Preview writes nothing.

Review recording appends only:

`logs/hammer_radar_forward/tiny_live_final_console.ndjson`

Controls arming can additionally update only:

`configs/hammer_radar/lane_controls.json`

R263 must not update risk contracts, signed request ledgers, strategy
promotion/performance, paper outcomes, env files, or external env files.

## Safety

R263 always reports:

- `final_console_only=true`
- `submit_allowed=false`
- `submit_attempted=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `binance_account_endpoint_called=false`
- `private_binance_endpoint_called=false`
- `signed_binance_endpoint_called=false`
- `hmac_signature_created=false`
- `signed_request_written=false`
- `secrets_shown=false`
- `secret_values_in_output=false`

When R262B is valid, signed triplet context is available, controls are armed,
and the experimental 8m short lane has been accepted, R263 points to
`R264_ACTUAL_SUBMIT_CHECKPOINT`. It still reports
`go_for_actual_submit_now=false`.

R264 is the next checkpoint and owns the actual-submit/reconciliation boundary:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile
```

R264B may call this R263 arming path internally after the exact R264B prep
phrase, using the exact R263 experimental-lane acceptance phrase. R264B remains
prep-only: it does not submit, place orders, call Binance order/private/account
endpoints, or change promotion state.
