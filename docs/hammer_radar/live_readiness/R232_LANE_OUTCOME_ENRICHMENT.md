# R232 Lane Outcome Enrichment

R232 adds a paper-only enrichment audit over the latest R231 full-spectrum lane scoreboard.
It keeps the official tiny-live lane unchanged:

`BTCUSDT|8m|short|ladder_close_50_618`

## Purpose

- Read the latest R231 full-spectrum lane scoreboard.
- Read local paper outcome, execution, strategy performance, promotion, and capture-count ledgers when present.
- Enrich lane rows with known/unknown outcome counts, win/loss rates, outcome coverage, freshness, sample quality, outcome quality score, capture readiness score, and combined watch score.
- Compare official tiny-live lane outcome quality against alternates without promoting anything.
- Keep capture readiness separate from outcome quality, so win rate alone cannot imply tiny-live readiness.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-outcome-enrichment
```

Record append-only enrichment:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-outcome-enrichment \
  --record-enrichment \
  --confirm-lane-outcome-enrichment "I CONFIRM LANE OUTCOME ENRICHMENT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected record attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-outcome-enrichment \
  --record-enrichment \
  --confirm-lane-outcome-enrichment "wrong"
```

## Scoring

`outcome_quality_score` is deterministic and watchlist-only:

- win-rate component: up to 60 points
- sample-size bonus: up to 20 points
- outcome-coverage bonus: up to 10 points
- freshness bonus: up to 5 points
- unknown-outcome penalty: up to 10 points
- blocker penalty: up to 15 points

`capture_readiness_score` is `unique_capture_count / threshold_required_count`, capped at `1.0`.

`combined_watch_score` is `70% outcome_quality_score + 30% capture_readiness_score`.
It is not a promotion score and does not authorize live trading.

## Ledger

`logs/hammer_radar_forward/lane_outcome_enrichment.ndjson`

This is append-only. Preview and rejected runs do not write records.

## Safety

R232 is diagnostic/audit only. It does not:

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
- rewrite paper outcome ledgers

All enriched rows force `live_authorized=false` and `promotion_allowed=false`.

## Follow-Up

R233 should use R232 enriched lane quality for paper-only capture/fishing priority recommendations without config writes, Binance/network calls, lane promotion, or live execution.
