# R233 Capture Priority Rebalance

R233 adds a paper-only capture priority rebalance audit over the latest R232 lane outcome enrichment, R231 full-spectrum lane scoreboard, 8m short capture sync, fisherman supervision, and betrayal/inverse shadow context.

It keeps the official protected tiny-live path unchanged:

`BTCUSDT|8m|short|ladder_close_50_618`

## Purpose

- Keep the official 8m short protected path first while it waits for 10/10 captures.
- Raise paper watch priority for near-threshold alternates such as 8m long without promotion.
- Separate outcome-strong capture-blocked lanes from tiny-sample traps.
- Preserve betrayal/inverse evidence as explicit shadow-priority context.
- Produce recommendations only; no runtime behavior changes.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-priority-rebalance
```

Record append-only rebalance:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-priority-rebalance \
  --record-rebalance \
  --confirm-capture-priority-rebalance "I CONFIRM CAPTURE PRIORITY REBALANCE RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected record attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-priority-rebalance \
  --record-rebalance \
  --confirm-capture-priority-rebalance "wrong"
```

## Priority Groups

- `OFFICIAL_PROTECTED_TINY_LIVE_PATH`
- `NEAR_THRESHOLD_ALTERNATE`
- `OUTCOME_STRONG_CAPTURE_BLOCKED`
- `BETRAYAL_SHADOW_PRIORITY`
- `TINY_SAMPLE_TRAP`
- `BLOCKED_OR_UNKNOWN`

Priority rank is paper-only guidance. It is not promotion, tiny-live readiness, funding readiness, risk-contract readiness, or live eligibility.

## Ledger

`logs/hammer_radar_forward/capture_priority_rebalance.ndjson`

This is append-only. Preview and rejected runs do not write records.

## Safety

R233 does not:

- call Binance or network
- place orders
- create executable order payloads
- sign requests
- mutate env files
- mutate configs
- write lane controls
- write risk contracts
- mutate fisherman or scheduler configs
- change lane modes
- set any lane `tiny_live`
- promote lanes, alternates, betrayal, or signal origins
- disable the kill switch
- infer funding readiness
- infer live readiness
- rewrite historical or paper outcome ledgers

All rows force `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.

## Follow-Up

- Continue waiting for the official 8m short protected path to reach 10/10.
- Run R228 only after the official protected path reaches 10/10 and the checklist preconditions remain clean.
- Run R234 to refresh betrayal/inverse shadow priority so 222m/88m evidence remains visible without config writes or live execution.
