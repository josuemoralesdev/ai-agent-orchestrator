# R193 Crow Outcome Mapping Preview

## Phase

R193 Crow Outcome Mapping Preview

## Purpose

Map Three Black Crows detections from local R189/R190/R191/R192 evidence to future paper outcome windows so the detector family can be evaluated before any promotion review.

## Scope

- Read local Three Black Crows detection records.
- Read local Three Black Crows paper tag records.
- Read local paper outcomes and paper execution records when available.
- Estimate post-detection behavior over bounded future paper windows.
- Report whether the crow pair has enough mapped paper outcomes for later review.

## Non-Negotiables

- No live execution.
- No config writes.
- No env writes or mutation.
- No Binance calls.
- No network calls.
- No order or test-order endpoints.
- No transfer or withdraw endpoints.
- No executable payloads.
- No signed requests.
- No signal-origin promotion.
- No lane promotion.
- No lane mode changes.
- No tiny-live arming.

## Expected Output

- target lane: `BTCUSDT|8m|short|ladder_close_50_618`
- target origin: `three_black_crows`
- detection count and tag count
- mapped outcome windows
- unmapped detections
- paper-only outcome summary
- recommendation for more mapping, more evidence, or later detector-family expansion
- safety object proving no live/config/network actions occurred

## Suggested Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  crow-outcome-mapping-preview
```
