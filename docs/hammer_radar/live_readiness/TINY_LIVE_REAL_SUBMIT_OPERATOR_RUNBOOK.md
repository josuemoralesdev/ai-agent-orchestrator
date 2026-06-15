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
6. Confirm R262B percentage risk-contract fit is valid when R262A reported
   `unsafe_limits`.
7. Confirm kill-switch does not block.
8. Confirm no duplicate live submit exists for the idempotency key.
9. Confirm exact order triplet:
   - main `SELL MARKET <latest R262B/R253B regenerated quantity>`
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
that blocker before arming. For the R263 path, do not reuse the older R261
arming phrase as final acceptance because the 8m short lane is paper-only and
promotion-mismatched by default.

## R262A Tiny-Live Risk Contract Fix And Controls Recheck

R262A diagnoses the R261 risk-contract blocker, records
`tiny_live_risk_contract_fix.ndjson`, and reuses R261 controls arming only when
the risk contract recheck is valid. It must not submit, sign, regenerate signed
requests, call Binance/network, place orders, or loosen risk limits.

If R262A reports `root_cause=unsafe_limits`, do not arm controls and do not open
R262 as submit-ready. A later authorized fresh cycle must produce a triplet that
is inside the same or stricter risk contract.

## R262B Percentage Risk Contract Fit

R262B converts the tiny-live contract to an equivalent percentage wallet model
and regenerates the signed triplet so quantity fits the resolved contract. The
current resolved limits remain `88 USDT` isolated wallet, `44 USDT` position
margin, `10x` leverage, `440 USDT` max notional, and `4.44 USDT` max loss.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit
```

Run and record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-percentage-risk-contract-fit \
  --run-contract-fit-regeneration \
  --record-contract-fit-regeneration \
  --confirm-contract-fit-regeneration "I CONFIRM TINY LIVE PERCENTAGE RISK CONTRACT FIT REGENERATION ONLY; 88 USDT ISOLATED WALLET, 44 USDT POSITION MARGIN, 10X LEVERAGE, KEEP RISK SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."
```

R262B does not arm controls and does not submit. If valid, the next operator
move is R263 final console review and experimental-lane-aware controls arming.

## R263 Final Console And Controls Arming

R263 displays R262B contract fit, signed triplet context, controls state,
promotion-ready lanes, readiness blockers, and lane/fisherman warnings in one
surface. It may append `tiny_live_final_console.ndjson`, and it may update only
`configs/hammer_radar/lane_controls.json` after this exact phrase:

```text
I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT EXPERIMENTAL LANE ONLY; I ACCEPT 8M SHORT IS PAPER-ONLY/PROMOTION-MISMATCHED; NO SUBMIT; NO ORDER; NO BINANCE CALL.
```

R263 must report `go_for_actual_submit_now=false`, `submit_allowed=false`, and
`operator_should_submit_now=false`. If it arms controls successfully, the next
step is R264 actual submit checkpoint, not real submit from R263.

## R264 Actual Submit And Immediate Reconciliation

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

Rejected live-submit safety check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-actual-submit-reconcile \
  --execute-actual-live-submit \
  --allow-binance-order-endpoint \
  --confirm-actual-live-submit "wrong"
```

This is a template only. It must be manually reviewed and pasted by the operator
only after the checklist is complete:

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

R264 records all dry previews, blocked/rejected execution attempts, actual
submit attempts, reconciliation results, and partial-success critical states in
`logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson`.

## R264B JIT Launch Packet

R264B is the compressed just-in-time prep lane for tonight/early-morning tiny
live. It runs R262B contract-fit regeneration, R263 experimental-lane controls
arming, and R264 dry preview under one exact phrase, then prints the final
manual live command only if the packet says GO.

R264B does not submit, place orders, call Binance order/test-order/account
endpoints, call private/signed Binance endpoints, or run the printed command.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet
```

Run JIT prep, still no submit:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-jit-launch-packet \
  --run-jit-launch-prep \
  --record-jit-launch-packet \
  --confirm-jit-launch-prep "I CONFIRM TINY LIVE JIT LAUNCH PREP ONLY; REFRESH CONTRACT-FIT TRIPLET, ARM R263 EXPERIMENTAL LANE, RUN R264 DRY PREVIEW; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL." \
  --operator-id local_operator \
  --reason "Final JIT prep for first tiny-live BTCUSDT 8m short experimental lane."
```

If `jit_go_no_go_packet.go_for_manual_live_submit_command=false`, do not run
the manual live command. If it is true, still review the final command and run
it manually only once outside Codex.

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
