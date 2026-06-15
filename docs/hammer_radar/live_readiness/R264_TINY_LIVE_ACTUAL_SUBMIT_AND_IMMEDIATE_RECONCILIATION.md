# R264 Tiny-Live Actual Submit And Immediate Reconciliation

R264 is the guarded actual-submit checkpoint for:

`BTCUSDT|8m|short|ladder_close_50_618`

It consumes the latest R262B contract-fit triplet and the latest R263 final
console controls arming/experimental-lane acceptance. Preview is the default.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile
```

Record dry preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --dry-run-actual-submit-reconcile \
  --record-actual-submit-preview \
  --confirm-actual-submit-dry-preview "I CONFIRM TINY LIVE R264 ACTUAL SUBMIT DRY PREVIEW ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Rejected live-submit example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --execute-actual-live-submit \
  --allow-binance-order-endpoint \
  --confirm-actual-live-submit "wrong"
```

Actual live-submit command template. Do not run unless the operator has just
verified R262B/R263/R264 readiness and intentionally accepts real order
placement:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --execute-actual-live-submit \
  --allow-binance-order-endpoint \
  --confirm-actual-live-submit "I CONFIRM TINY LIVE BTCUSDT 8M SHORT ACTUAL SUBMIT; USE LATEST R262B CONTRACT-FIT SIGNED TRIPLET ONLY; MAIN SELL MARKET 0.006 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS." \
  --operator-id local_operator \
  --reason "R264 actual tiny-live submit after R262B contract-fit and R263 final console arming."
```

## Validation

R264 blocks unless all are true:

- latest R262B contract fit is valid
- latest R263 experimental-lane acceptance exists
- lane controls are armed for the exact 8m short lane at runtime
- latest signed triplet has exactly three `/fapi/v1/order` requests
- main order is `SELL MARKET 0.006`
- stop and take-profit are `BUY` reduce-only exit orders
- signed triplet is fresh
- idempotency has no prior live submit for the same signed triplet
- exact live phrase and explicit endpoint allow flag are supplied for execution

## Ledger

R264 appends only:

`logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson`

Dry previews, rejected attempts, blocked attempts, actual execution attempts,
reconciliation results, and partial-success critical states are recorded there.

## API And UI

- `GET /tiny-live/actual-submit/reconcile`
- `POST /tiny-live/actual-submit/dry-preview`
- `POST /tiny-live/actual-submit/execute`

The dashboard includes a Tiny Live Actual Submit Checkpoint card. It has no
auto-submit behavior. Execute requires the exact phrase and explicit endpoint
allow flag.

## Partial Success

If one or two orders submit but all three do not reconcile, R264 records
`TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_CRITICAL`, marks recovery required,
and tells the operator not to resubmit the main order. R264 does not place
recovery orders or cancellations automatically.

The required follow-up is:

`R265_TINY_LIVE_POST_LIVE_HARDENING_AND_RECOVERY`

## Safety

Preview/tests must report no Binance order/private/account calls, no secret
printing, no env/config/risk/lane mutation, no paper/live separation break, and
no order placement.
