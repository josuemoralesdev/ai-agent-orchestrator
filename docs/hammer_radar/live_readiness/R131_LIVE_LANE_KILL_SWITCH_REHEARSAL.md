# R131 Live Lane Kill-Switch Rehearsal

Phase: R131

## What R131 Adds

R131 adds a non-executing rehearsal layer for the selected autonomous lane:

`src/app/hammer_radar/operator/live_lane_kill_switch_rehearsal.py`

It proves, in preview or append-only rehearsal-record mode, that the system can stop, disable, rollback, and block a lane before that lane is allowed to operate as `tiny_live`.

Primary command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-lane-kill-switch-rehearsal \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

## What R131 Does Not Add

R131 does not place orders, create Binance order payloads, call Binance order endpoints, sign requests, mutate `.env`, mutate `configs/hammer_radar/lane_controls.json`, enable global live flags, install/start scheduler services, create a live order endpoint, or implement live adapter behavior.

The only write path is an append-only rehearsal record:

`logs/hammer_radar_forward/live_lane_kill_switch_rehearsals.ndjson`

## Why This Comes Before Live

The lane needs a proven stop path before any tiny-live promotion can be considered. R131 rehearses the transition from `armed_dry_run` or `paper` toward `tiny_live` intent, then proves that lane disable, global kill switch, rollback, and scheduler/autonomy checks stop live/tiny-live intent without config or env mutation.

## Global Kill Switch, Lane Disable, Rollback

- Global kill switch rehearsal simulates global live-intent blocking and verifies paper/live separation remains intact.
- Lane disable rehearsal simulates the selected lane as `disabled` in memory and verifies router/autonomy decisions become blocked or ignored.
- Rollback rehearsal simulates a lane moving from `tiny_live` back to `armed_dry_run` or `disabled` and verifies R126 remains blocked and the scheduler/autonomy path stops producing tiny-live review.

## Scheduler Behavior

R131 reuses the R127/R128 decision semantics to prove disabled or killed lanes are stopped or blocked. It does not install, start, stop, or edit any scheduler service.

## Paper Proof Gap

R130 currently remains blocked by missing recent autonomous paper proof. R131 reports the safe R129 command template for producing that proof, but does not run it automatically:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  autonomous-paper-lane-executor-integration \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-paper \
  --confirm-paper-integration "I CONFIRM AUTONOMOUS PAPER LANE INTEGRATION ONLY; NO REAL ORDER; NO BINANCE CALL."
```

## Tiny-Live Lane Mode Gap

R126 currently remains blocked because no selected lane is configured as `tiny_live`. R131 reports safe preview commands for R124/R130 only. Actual lane mode changes remain R124-controlled and require the R124 phrase:

`I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE.`

R130 authorization intent remains separate and requires:

`I CONFIRM TINY LIVE LANE AUTHORIZATION ONLY; NO ORDER; NO BINANCE CALL.`

## Rehearsal Recording

Preview is the default and writes no ledger. Recording requires:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-lane-kill-switch-rehearsal \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-rehearsal \
  --confirm-rehearsal-record "I CONFIRM KILL SWITCH REHEARSAL RECORDING ONLY; NO ORDER; NO CONFIG CHANGE."
```

Wrong or missing confirmation returns `KILL_SWITCH_REHEARSAL_REJECTED` and writes nothing.

## Next Phases

- R132 live adapter boundary final review.
- R133 lane control cockpit UI.
- R134 first tiny-live order payload dry authorization.
