# R231 Full-Spectrum Lane Scoreboard / Tiny-Live Alternate Candidate Audit

R231 adds a paper-only full-spectrum lane scoreboard for local Hammer Radar evidence.
It keeps the official tiny-live lane unchanged:

`BTCUSDT|8m|short|ladder_close_50_618`

## Purpose

- Read local full-spectrum harvest, short capture, signal flow, paper outcome, strategy performance, strategy promotion, and 8m short capture-count sync ledgers.
- Normalize lanes as `symbol|timeframe|direction|entry_mode`.
- Use `entry_unknown` when entry mode is missing.
- Count signal flow, capture events, unique captured signal IDs, outcomes, known wins/losses, win rate, freshness, and threshold distance per lane.
- Report alternate tiny-live watchlist lanes without changing lane mode or promoting anything.
- Preserve the official tiny-live lane and all live-trading protections.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  full-spectrum-lane-scoreboard
```

Record append-only scoreboard:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  full-spectrum-lane-scoreboard \
  --record-scoreboard \
  --confirm-full-spectrum-lane-scoreboard "I CONFIRM FULL SPECTRUM LANE SCOREBOARD RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected record attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  full-spectrum-lane-scoreboard \
  --record-scoreboard \
  --confirm-full-spectrum-lane-scoreboard "wrong"
```

## Ledger

`logs/hammer_radar_forward/full_spectrum_lane_scoreboard.ndjson`

This is append-only. Preview and rejected runs do not write records.

## Safety

R231 is diagnostic/audit only. It does not:

- call Binance or network
- place orders
- create executable order payloads
- sign requests
- mutate env files
- mutate configs
- write lane controls
- write risk contracts
- change lane modes
- set any lane `tiny_live`
- promote lanes or signal origins
- disable the kill switch
- infer funding readiness
- infer live readiness

All output rows force `live_authorized=false` and `promotion_allowed=false`.

## Follow-Up

R232 should enrich top scoreboard lanes with paper outcomes, known win/loss counts, and promotion blockers without config writes, Binance/network calls, or live execution.
