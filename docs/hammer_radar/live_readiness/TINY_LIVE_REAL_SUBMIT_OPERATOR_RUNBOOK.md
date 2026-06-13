# Tiny-Live Real Submit Operator Runbook

This runbook is for the official lane:

`BTCUSDT|8m|short|ladder_close_50_618`

It is a manual operator procedure. Codex must not submit, call Binance, sign,
regenerate signed requests, mutate live controls, disable kill switches, or
place orders while preparing or recording this runbook.

## Pre-Submit Checklist

1. Run R253 final readonly mark refresh.
2. If the signed request timestamp would be stale, run R253B fresh context signed request regeneration.
3. Run R254 submit gate preview.
4. Run R255 actual submit gate dry preview immediately before any manual submit.
5. Confirm lane/tiny-live controls are intentionally armed.
6. Confirm kill-switch does not block.
7. Confirm no duplicate live submit exists for the idempotency key.
8. Confirm exact order triplet:
   - main `SELL MARKET 0.007`
   - stop `BUY STOP_MARKET reduceOnly true`
   - take-profit `BUY TAKE_PROFIT_MARKET reduceOnly true`
9. Review the post-submit reconciliation checklist.
10. Review partial-success and abort handling before any manual command paste.

## R256 Packet Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook
```

Record the runbook packet only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-real-submit-runbook \
  --record-operator-real-submit-runbook \
  --confirm-tiny-live-operator-runbook "I CONFIRM TINY LIVE OPERATOR RUNBOOK RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

## R257 Final Pre-Submit Arming Drill

R257 is the final drill packet before any manual submit checkpoint. It does not
arm live controls, regenerate signed requests, call Binance, submit, or place
orders.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill
```

Record the final drill packet only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-pre-submit-arming-drill \
  --record-final-pre-submit-arming-drill \
  --confirm-tiny-live-final-pre-submit-arming-drill "I CONFIRM TINY LIVE FINAL PRE-SUBMIT ARMING DRILL RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

R257 must report `operator_should_submit_now=false`. If the signed request is
stale, regenerate before any further checkpoint. If lane controls or live
execution remain off, the operator must arm them manually outside Codex before
any later manual submit decision.

## R258 Manual Submit Checkpoint

R258 is the final manual checkpoint packet before a later fresh-cycle checkpoint.
It does not arm live controls, regenerate signed requests, sign, call Binance,
submit, or place orders.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-submit-checkpoint
```

Record the manual checkpoint only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-submit-checkpoint \
  --record-manual-submit-checkpoint \
  --confirm-tiny-live-manual-submit-checkpoint "I CONFIRM TINY LIVE MANUAL SUBMIT CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

R258 must report `operator_should_submit_now=false`. If the signed request is
stale, run a fresh cycle before any later manual submit decision. If lane
controls or live execution remain off, the operator must review and arm them
manually outside Codex before any later manual submit decision.

## R255 Manual Submit Template

This is a template only. It must be manually reviewed and pasted by the operator
only after the checklist is complete:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-actual-submit-gate --execute-actual-submit --allow-real-binance-order-endpoint --confirm-tiny-live-actual-submit "I CONFIRM TINY LIVE BTCUSDT 8M SHORT SUBMIT ONLY; PLACE EXACTLY THREE BINANCE FUTURES ORDERS FROM LATEST R253B SIGNED REQUEST; MAIN SELL MARKET 0.007 BTC; STOP BUY STOP_MARKET REDUCE_ONLY; TAKE_PROFIT BUY TAKE_PROFIT_MARKET REDUCE_ONLY; NO OTHER ORDERS."
```

## Reconciliation

- Record all exchange order ids.
- Verify main order status.
- Verify stop reduceOnly order status.
- Verify take-profit reduceOnly order status.
- Verify no extra orders.
- Verify live execution ledger append.
- Verify idempotency key recorded.

## Partial Success

- Main fails: stop, reconcile accepted exit orders, cancel orphan exits if no matching position exists.
- Main succeeds and stop fails: treat as unprotected and require manual protective stop decision before any further action.
- Main succeeds and take-profit fails: verify stop protection before any take-profit retry.
- Exit duplicate: inspect exchange open orders before retry.
- Unknown exchange response: do not retry until order history and current position are reconciled.

## Abort

- Before submit: abort on stale signed request, non-armed controls, kill-switch block, duplicate idempotency, or missing reconciliation plan.
- After partial submit: stop retries and reconcile exchange state first.
- After full submit: verify exactly one main and two reduceOnly exits.
- If reconciliation fails: do not submit again; preserve evidence and escalate to manual cleanup.
