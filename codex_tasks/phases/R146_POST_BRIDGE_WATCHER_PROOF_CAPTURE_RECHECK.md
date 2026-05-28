# R146 Post-Bridge Watcher Proof Capture Recheck

## Phase

`R146`

## Branch

`r146-post-bridge-watcher-proof-capture-recheck`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION
- Duplicate risk level: HIGH

## Main Objective

Rerun the R142 watcher path after R145 entry-mode derivation bridge is in place and verify whether fresh normalized watched-lane candidates are now visible when market conditions occur.

## Scope

Use only:

- `entry-mode-derivation-bridge`
- `signal-to-watcher-eligibility-trace`
- `fresh-candidate-paper-proof-capture-loop`
- existing R129/R140 paper proof path

Do not add lanes, shorts, live execution, Binance calls, order payloads, env mutation, config mutation, global flag mutation, or service changes.

## Required Checks

1. Preview R145 bridge status for all unlocked lanes.
2. Rerun R144 trace and confirm post-bridge fields show normalized watched lane keys when applicable.
3. Rerun R142 watcher preview.
4. If a fresh normalized watched candidate appears and R129/R140 says it is eligible, capture paper proof through the existing R142 -> R140 -> R129 path only.
5. If the candidate is stale, report stale only.
6. If no watched candidate is present, report wait state only.

## Safety Constraints

- No Binance.
- No live execution.
- No order placement.
- No executable or protective payloads.
- No signed requests.
- No env edits.
- No config edits.
- No global flag changes.
- Do not widen R143 unlocked lanes.

## Suggested Commands

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  entry-mode-derivation-bridge \
  --trace-all-unlocked-lanes
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-to-watcher-eligibility-trace \
  --trace-all-unlocked-lanes
```

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fresh-candidate-paper-proof-capture-loop \
  --watch-all-recommended-lanes
```

## Expected Output

Report whether R145 made fresh `BTCUSDT|13m|long|ladder_close_50_618` or `BTCUSDT|44m|long|ladder_close_50_618` candidates visible to R142/R129, and whether any paper proof was captured through the existing safe path.
