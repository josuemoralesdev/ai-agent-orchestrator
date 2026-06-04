# R181 Multi-Lane Evidence Ranking and Next Door Selection

## Purpose

Rank expanded BTCUSDT paper lanes using R180 multi-lane harvester records, compare `BTCUSDT|8m|short|ladder_close_50_618` against all active paper lanes, and select the next best tiny-live candidate door for review.

## Scope

- Read `logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson`.
- Read R180 lane capture counts and recommendations.
- Compare fresh captures, recent fresh flow, stale/blocked counts, and threshold state by lane.
- Preserve tiny-live incumbents as reference-only context.
- Emit a diagnostic ranking and next-door recommendation.

## Non-Negotiables

- No live execution.
- No Binance calls.
- No order or protective payloads.
- No signed requests.
- No env writes.
- No config writes.
- No lane mode changes.
- Do not set any lane `tiny_live`.
- Do not write risk contract config.
- Do not transfer or withdraw.

## Expected Output

- ranked lanes
- 8m short versus best alternate lane comparison
- threshold-met lanes
- next evidence-readiness review candidate
- recommended next operator move
- recommended next engineering move
- safety object with all live/order/config/network mutation flags false

## Suggested CLI

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  multi-lane-evidence-ranking
```
