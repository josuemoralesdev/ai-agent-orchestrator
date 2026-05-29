# R147 Fast Lane Tiny-Live Mode Intent Path

Phase: R147

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Why R147 Exists

R147 fixes the R124 `lane-control-command` path for tiny-live mode intent. Previewing or applying a lane mode change is an operator-owned config-intent action, so it must stay fast and bounded.

Before R147, a tiny-live preview could evaluate `evaluate_lane_permission()` without an injected global gate. That caused the command to load the full first-live activation gate chain, including final preflight and downstream Markov/candle archive surfaces. That deep review belongs to explicit gate review commands, not lane mode preview/apply.

## Intent Is Not Permission

Setting a lane mode to `tiny_live` means:

```text
TINY_LIVE_LANE_WAITING_FOR_CONDITIONS
```

It does not mean:

```text
LIVE_ORDER_READY
FIRST_LIVE_ACTIVATION_READY
ORDER_PLACED
```

Lane mode is operator intent only; it is not execution permission. R106/global gates, paper proof, freshness, protective policy, authorization, and kill-switch state remain authoritative before any future tiny-live execution path.

## Fast Global Gate Sentinel

R147 adds a lightweight global gate sentinel for lane mode preview/apply:

```json
{
  "status": "GLOBAL_GATE_NOT_EVALUATED_FAST_LANE_MODE_PATH",
  "ready": false,
  "execution_enabled": false,
  "global_kill_switch_active": true,
  "allow_live_orders": false,
  "blockers": [
    "global gate not evaluated in fast lane mode path",
    "live execution remains disabled",
    "global kill switch remains authoritative"
  ]
}
```

The sentinel lets `evaluate_lane_permission()` report a tiny-live lane as blocked by global gates without calling `build_first_live_activation_gate()`.

## Why The First-Live Gate Is Not Called

The first-live activation gate is a deep non-executing readiness review. It composes heavier safety surfaces and can take much longer than an operator mode-intent preview should take.

R147 keeps the default `lane-control-command --action set-mode --mode tiny_live --request-tiny-live` path fast by passing the sentinel into lane permission evaluation. Operators should use the existing first-live and tiny-live gate commands when they explicitly want a deep review.

## Commands

Preview 13m:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live
```

Preview 44m:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live
```

Confirmed apply still requires the existing R124 phrase:

```text
I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE.
```

## Safety Constraints

R147 does not place orders, create executable order payloads, create protective order payloads, call Binance, send signed requests, mutate env files, change global live flags, disable the kill switch, bypass R106/global gates, bypass protective policy, bypass freshness, create fake paper proof, widen lanes, or add shorts.

The fast path reports:

- lane mode is operator intent only; it is not execution permission
- global gates were not deeply evaluated in fast lane mode path
- live execution remains disabled
- global kill switch remains authoritative

## Next Operator Step

After merge, R148 should apply the `tiny_live` lane mode intent for the 13m and 44m lanes through the fixed fast path, then recheck lane status, tiny-live gates, and post-bridge watcher proof readiness. R148 must remain non-executing and must not call Binance or mutate global live flags.
