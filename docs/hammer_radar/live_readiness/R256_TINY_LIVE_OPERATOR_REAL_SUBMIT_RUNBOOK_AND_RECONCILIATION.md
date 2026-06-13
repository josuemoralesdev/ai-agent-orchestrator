# R256 Tiny-Live Operator Real Submit Runbook And Reconciliation

R256 creates the operator runbook and reconciliation packet for the final manual
R255 tiny-live real-submit event on:

`BTCUSDT|8m|short|ladder_close_50_618`

This phase does not submit, call Binance, call order endpoints, sign, regenerate
signed requests, read API keys, mutate live controls, or place orders. It is
documentation plus one local runbook ledger append after exact confirmation.

## Current R255 Blockers

The latest R255 dry preview is expected to block real submit on:

- `signed_request_timestamp_stale`
- `official_lane_not_tiny_live`
- `live_execution_not_enabled`

R256 intentionally preserves those blockers and makes the next manual operator
steps explicit.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook
```

Record runbook only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook \
  --record-operator-real-submit-runbook \
  --confirm-tiny-live-operator-runbook "I CONFIRM TINY LIVE OPERATOR RUNBOOK RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Rejected recording proof:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook \
  --record-operator-real-submit-runbook \
  --confirm-tiny-live-operator-runbook "wrong"
```

## Required Operator Sequence Before Any Manual Real Submit

1. Run a fresh final readonly mark refresh.
2. Regenerate signed request if timestamp would be stale.
3. Confirm lane/tiny-live controls are intentionally armed.
4. Confirm kill-switch does not block.
5. Confirm no duplicate live submit exists for the idempotency key.
6. Confirm exact triplet:
   - main `SELL MARKET 0.007`
   - stop `BUY STOP_MARKET reduceOnly true`
   - TP `BUY TAKE_PROFIT_MARKET reduceOnly true`
7. Run R255 dry preview immediately before real submit.
8. Only then consider manually pasting the exact R255 live submit command.

## Manual Submit Template

R256 emits the R255 command as a template only. Codex must not auto-run it:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-actual-submit-gate --execute-actual-submit --allow-real-binance-order-endpoint --confirm-tiny-live-actual-submit "I CONFIRM TINY LIVE BTCUSDT 8M SHORT SUBMIT ONLY; PLACE EXACTLY THREE BINANCE FUTURES ORDERS FROM LATEST R253B SIGNED REQUEST; MAIN SELL MARKET 0.007 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS."
```

## Reconciliation Checklist

- record exchange order ids
- verify main order status
- verify stop reduceOnly order status
- verify take-profit reduceOnly order status
- verify no extra orders
- verify live execution ledger append
- verify idempotency key recorded

## Partial Success Handling

- If main fails: do not retry automatically; verify whether any exit order was accepted; cancel orphan reduceOnly exits if there is no matching position.
- If main succeeds and stop fails: treat the position as unprotected; verify or place protective stop manually before further action.
- If main succeeds and take-profit fails: verify stop reduceOnly protection is live before any take-profit retry.
- If an exit order duplicates: inspect exchange open orders before retrying.
- If exchange response is unknown: do not retry; reconcile exchange order history and positions first.

## Abort And Cleanup

- Abort before submit if signed request is stale, lane controls are not intentionally armed, kill-switch blocks, or prior live submit exists.
- After partial submit, stop retries, reconcile accepted ids and current position, and ensure stop protection exists if the main order filled.
- After full submit, record all three ids and verify only one main order plus two reduceOnly exits exist.
- If reconciliation fails, do not submit again; preserve logs and escalate to manual cleanup and engineering review.

## Ledger

Confirmed R256 records append only:

`logs/hammer_radar_forward/tiny_live_operator_real_submit_runbook.ndjson`

Preview and bad-confirmation paths write no R256 ledger.

## Safety

R256 preserves:

- `operator_runbook_only=true`
- `submit_allowed=false`
- `submit_attempted=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `network_allowed=false`
- `hmac_signature_created=false`
- `signed_request_written=false`
- `secrets_read=false`
- `secrets_shown=false`
- `secrets_persisted=false`
- no env/config/lane-control/live-control mutation

## Next Phase

R257 should be the final pre-submit arming drill. It must still not submit; it
should verify R256 review, intended live controls state, regeneration freshness,
known exact R255 command, and produce a final manual decision packet.
