# R148 Apply Tiny-Live Lane Mode And Recheck Gates

Phase: R148

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Why R148 Follows R147

R147 made `lane-control-command` safe and fast for `tiny_live` lane mode intent by using the fast global gate sentinel instead of loading the heavy first-live activation gate chain during lane mode preview/apply.

R148 does not add a second lane mutation path. It creates an operator runbook and recheck ledger around the existing R147 path for the already-unlocked target lanes:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

## Tiny-Live Lane Mode Is Intent Only

`tiny_live` lane mode means lane intent:

```text
TINY_LIVE_LANES_WAITING_FOR_CONDITIONS
```

It is not:

```text
LIVE_ORDER_READY
FIRST_LIVE_ACTIVATION_READY
ORDER_PLACED
```

R106/global gates, kill switch state, fresh normalized candidates, autonomous paper proof, protective policy, and future explicit authorization remain authoritative.

## R148 Preview

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  apply-tiny-live-lane-mode-recheck \
  --all-target-lanes \
  --include-apply-commands \
  --include-post-apply-recheck-commands
```

## R148 Recording Only

This records the R148 runbook/recheck only. It does not apply lane mode, mutate config, call Binance, or authorize live execution.

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  apply-tiny-live-lane-mode-recheck \
  --all-target-lanes \
  --include-apply-commands \
  --include-post-apply-recheck-commands \
  --record-recheck \
  --confirm-recheck "I CONFIRM TINY LIVE LANE MODE RECHECK RECORDING ONLY; NO ORDER; NO BINANCE CALL."
```

## Human-Run Apply Commands

Codex must not run these commands against the real config. The human operator runs them after merge on main if the preview is acceptable.

13m:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live \
  --apply \
  --confirm-lane-change "I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE."
```

44m:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live \
  --apply \
  --confirm-lane-change "I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE."
```

## Post-Apply Recheck Commands

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-status
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-lane-execution-gate \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-lane-execution-gate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618"
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  post-bridge-watcher-proof-capture-recheck \
  --trace-all-unlocked-lanes
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  binance-readonly-status
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-safety
```

Safe 60-minute watcher:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fresh-candidate-paper-proof-capture-loop \
  --watch-all-recommended-lanes \
  --max-iterations 60 \
  --sleep-seconds 60 \
  --run-watch-loop \
  --record-watch \
  --confirm-watch-loop "I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL."
```

## Expected Blockers After Apply

After the human applies lane mode on main, the expected state is `TINY_LIVE_LANES_WAITING_FOR_CONDITIONS`.

Expected remaining blockers:

- fresh autonomous paper proof missing
- fresh normalized candidate missing
- global gates not ready
- kill switch active
- live flags disabled

## Safety Boundary

R148 does not place orders, create executable Binance payloads, create protective payloads, call Binance order/test-order/protective endpoints, send signed requests, mutate env files, mutate global live flags, disable the kill switch, bypass R106/global gates, bypass protective policy, bypass freshness, or create fake paper proof.

The R148 ledger path is:

```text
logs/hammer_radar_forward/tiny_live_lane_mode_rechecks.ndjson
```

## Next Step After Fresh Paper Proof

After target lanes are `tiny_live` and a fresh normalized candidate paper proof is captured, re-run:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  first-tiny-live-lane-execution-gate \
  --lane-key "<fresh-proof-lane-key>"
```

That remains a non-executing gate review. Any live execution path still requires a future explicit phase and operator authorization.
