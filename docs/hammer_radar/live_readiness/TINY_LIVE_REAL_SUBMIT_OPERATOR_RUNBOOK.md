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
6. Confirm R262A risk-contract recheck is valid.
7. Confirm kill-switch does not block.
8. Confirm no duplicate live submit exists for the idempotency key.
9. Confirm exact order triplet:
   - main `SELL MARKET 0.007`
   - stop `BUY STOP_MARKET reduceOnly true`
   - take-profit `BUY TAKE_PROFIT_MARKET reduceOnly true`
10. Review the post-submit reconciliation checklist.
11. Review partial-success and abort handling before any manual command paste.

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

## R259 Fresh Cycle Checkpoint

R259 coordinates the required fresh cycle after R258. It does not run R253,
R253B, R254, R255, or R258 automatically. It does not call Binance, sign,
regenerate signed requests, submit, place orders, or arm live controls.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint
```

Record the fresh-cycle checkpoint only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-checkpoint \
  --record-fresh-cycle-checkpoint \
  --confirm-tiny-live-fresh-cycle-checkpoint "I CONFIRM TINY LIVE FRESH CYCLE CHECKPOINT RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

R259 must report `operator_should_submit_now=false`. When R253/R253B/R255 are
stale relative to R258, it should point first to R253 final readonly refresh,
then R253B regeneration, R254 preview, R255 dry preview, and R258 re-check.

## R260 Fresh Cycle One-Shot Orchestrator

R260 compresses the required fresh-cycle sequence into one exact-confirmed
orchestration command. It may run R253 public readonly refresh, R253B local
signed-request regeneration, R254 preview recording, R255 dry-preview recording,
and R258 re-check recording. It must not submit, call Binance order/account
endpoints, place orders, arm live controls, or mutate lane/risk/env config.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot
```

Run and record the one-shot fresh cycle only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-fresh-cycle-one-shot \
  --run-fresh-cycle-one-shot \
  --record-fresh-cycle-one-shot \
  --confirm-tiny-live-fresh-cycle-one-shot "I CONFIRM TINY LIVE FRESH CYCLE ONE-SHOT ORCHESTRATION ONLY; REFRESH READONLY MARKET, REGENERATE LOCAL SIGNED REQUEST, RECORD PREVIEWS; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."
```

R260 must report `operator_should_submit_now=false`. If the one-shot succeeds,
the next step is live-control review / R261 UI arming, not real submit from
R260.

## R261 Tiny-Live Controls Arming UI And API

R261 reviews R260/R255 freshness, lane controls, live execution state, kill
switch state, and the official lane risk contract. It may record review intent,
and it may arm only the official lane controls row after the exact arming
confirmation. It must not submit, sign, regenerate signed requests, call
Binance, place orders, update risk contracts, or disable a global kill switch.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming
```

Record controls review only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --record-controls-review \
  --confirm-tiny-live-controls-review "I CONFIRM TINY LIVE CONTROLS REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
```

Arm official lane controls only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-controls-arming \
  --arm-tiny-live-controls \
  --confirm-arm-tiny-live-controls "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL." \
  --operator-id local_operator \
  --reason "R260 fresh cycle valid; preparing for R262 final submit console."
```

R261 must report `submit_still_forbidden=true` and
`operator_should_submit_now=false`. If the risk contract remains invalid, fix
that blocker before arming. If R261 arms controls successfully, the next step is
R262 final submit console, not real submit from R261.

## R262A Tiny-Live Risk Contract Fix And Controls Recheck

R262A diagnoses the R261 risk-contract blocker, records
`tiny_live_risk_contract_fix.ndjson`, and reuses R261 controls arming only when
the risk contract recheck is valid. It must not submit, sign, regenerate signed
requests, call Binance/network, place orders, or loosen risk limits.

If R262A reports `root_cause=unsafe_limits`, do not arm controls and do not open
R262 as submit-ready. A later authorized fresh cycle must produce a triplet that
is inside the same or stricter risk contract.

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
