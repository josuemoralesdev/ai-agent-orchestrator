# R145 Entry Mode Derivation Bridge

R145 fixes the signal-to-watcher gap proven by R144: recent `BTCUSDT` 13m/44m long signal records can match watched lane symbol, timeframe, and direction while carrying `entry_mode=null`.

The R142/R129 paper proof path evaluates lane keys as:

```text
symbol|timeframe|direction|entry_mode
```

For the R143 unlocked lanes, the required key is:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

## R144 Finding

R144 showed visible signals with missing `entry_mode`, including a 44m long signal where the router could derive:

```text
ladder_close_50_618
```

and therefore the watched lane key:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

The remaining blocker was not live execution. It was runtime candidate normalization before watcher and paper eligibility preview.

## Runtime Normalization Rules

R145 adds `operator.entry_mode_derivation_bridge`.

The bridge:

- normalizes only `BTCUSDT`
- normalizes only watched 13m/44m long lanes
- requires lanes from the R143 unlock contract or explicit CLI lane keys
- preserves any existing `entry_mode`
- derives `entry_mode=ladder_close_50_618` only when the watched lane matches symbol/timeframe/direction
- derives the candidate lane key in memory
- marks `derived_entry_mode=true` and `derivation_source=R145_ENTRY_MODE_DERIVATION_BRIDGE`
- leaves raw `signals.ndjson` and historical ledgers untouched

## Freshness Boundary

The bridge does not bypass freshness.

A stale signal may be normalized into a lane key for diagnostics, but R123/R127/R129/R142 still block it as stale. The bridge reports `freshness_status_after_bridge` and `bridge_would_still_block_reason` so the operator can distinguish a solved entry-mode gap from an expired candidate.

## Paper Proof Boundary

The bridge does not create paper proof.

R142 can only capture proof through the existing R140/R129 path after the existing router, autonomy, scheduler, paper executor, and safety checks agree. R145 only makes missing-entry-mode watched-lane candidates addressable by that path.

## Live Execution Boundary

R145 does not authorize live execution.

It does not create order payloads, protective payloads, signed requests, Binance calls, env mutations, config mutations, global flag changes, lane widening, short lanes, or kill-switch changes.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  entry-mode-derivation-bridge \
  --trace-all-unlocked-lanes
```

Record diagnostic bridge status only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  entry-mode-derivation-bridge \
  --trace-all-unlocked-lanes \
  --record-bridge \
  --confirm-bridge "I CONFIRM ENTRY MODE DERIVATION BRIDGE RECORDING ONLY; NO ORDER; NO BINANCE CALL."
```

Post-bridge R144 trace:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-to-watcher-eligibility-trace \
  --trace-all-unlocked-lanes
```

Post-bridge R142 preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fresh-candidate-paper-proof-capture-loop \
  --watch-all-recommended-lanes
```

## Expected Post-R145 Behavior

When a fresh `BTCUSDT` 13m/44m long signal has `entry_mode=null`, R145 can derive `ladder_close_50_618`, build the watched lane key, and let the existing R142/R129 preview path evaluate it.

If the signal is fresh and otherwise eligible, R142 can proceed through the existing paper proof capture path. If the signal is stale, it remains blocked as stale.
