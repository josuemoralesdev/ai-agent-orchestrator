# R146 Post-Bridge Watcher Proof Capture Recheck

R146 follows R145 because R145 closed the entry-mode gap identified by R144: `BTCUSDT` 13m/44m long signals can now be normalized in memory into the R143 watched lane keys when `entry_mode` is missing.

The watched lane keys remain:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

## What Changed After R145

R145 did not create paper proof or live execution authority. It only made runtime candidates addressable by the existing watcher and paper preview paths:

- R142 watcher loop
- R129 paper executor integration preview/record path
- R140 safe clearing pack delegation into R129
- R143 unlock-contract lane selection

R146 rechecks those existing surfaces after the bridge. It reports whether normalized watched-lane candidates are visible, whether any are fresh, whether paper proof has already been captured, and which safe operator move comes next.

## Freshness Boundary

Stale remains blocked.

R146 counts normalized watched-lane candidates separately as fresh or stale. A stale candidate can prove that R145 derived the correct lane key, but it does not become proof-eligible. The next move for all-stale normalized candidates is `WAIT_FOR_FRESH_NORMALIZED_CANDIDATE`.

## Safe R142 Run After The Bridge

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  post-bridge-watcher-proof-capture-recheck \
  --trace-all-unlocked-lanes
```

Record the diagnostic recheck only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  post-bridge-watcher-proof-capture-recheck \
  --trace-all-unlocked-lanes \
  --record-recheck \
  --confirm-post-bridge-recheck "I CONFIRM POST BRIDGE WATCHER RECHECK RECORDING ONLY; NO ORDER; NO BINANCE CALL."
```

If R146 returns `RUN_R142_WATCHER` or `WAIT_FOR_FRESH_NORMALIZED_CANDIDATE`, the safe bounded watcher command is:

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

R142 still captures paper proof only through R140/R129 after existing freshness, lane, autonomy, paper, and safety checks.

## R147 Trigger

R147 should be built only after paper proof is captured through the existing watcher/paper path. R146 signals that condition with:

```text
BUILD_R147_AFTER_PAPER_PROOF_RECHECK
```

That next phase must re-evaluate R126/R130/protective/global gates and confirm the R143 lanes are still unlocked before any tiny-live condition-ready review.

## Live Execution Boundary

R146 has no live execution behavior. It does not place orders, create executable Binance or protective payloads, sign requests, call Binance order/test/protective/account/balance/private endpoints, mutate env/config, change global live flags, disable kill switches, bypass freshness, widen lanes, or add shorts.
