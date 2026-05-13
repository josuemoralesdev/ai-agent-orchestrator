# R81.3 Safe Candle Capture / Backfill Source

## Purpose

R81.3 adds the safe candle capture/backfill source needed by the R81.2 archive bridge and R81.1 resolver. It gives Hammer Radar a local path to write real OHLC candles into:

```text
logs/hammer_radar_forward/candle_archive/
```

R81.3 is local evidence plumbing only. It does not place orders, call Binance trading/live endpoints, expose secrets, edit env files, restart services, or make betrayal strategies live-ready.

## Why R81.3 Follows R81.2

R81.2 created the archive bridge, but dry-run smoke found no source files:

```text
discovered_sources=[]
files_scanned=0
candles_found=0
candles_written=0
```

R81.3 locates the runtime candle-producing path and adds a capture hook for future radar cycles.

## Candle-Producing Path Found

Hammer Radar runtime builds resampled OHLC frames in:

```text
src/app/hammer_radar/main.py
```

The loop uses `MarketReader.get_resampled(...)` to create per-timeframe candle frames. R81.3 archives those resampled candles through:

```text
capture_resampled_frames(...)
```

This is local archive writing only. It does not add network behavior beyond whatever the existing radar reader already does during normal radar operation.

## Local-Only Backfill Policy

The R81.3 backfill command defaults to:

```text
source_mode=LOCAL_ONLY
dry_run=true
write=false
```

It scans only local candle-shaped NDJSON sources that R81.2 understands. If no local source exists, it reports zero candles honestly.

No read-only market fetch path is enabled in R81.3.

## Archive Write Behavior

Archive files use the R81.2 format:

```text
candle_archive/{symbol}_{timeframe}.ndjson
```

Writes are local, deterministic, and deduped by:

```text
symbol + timeframe + open_time
```

Backfill writes only when both are true:

```text
dry_run=false
write=true
```

Runtime capture writes the resampled candles already present in memory during radar operation.

## Target Coverage

R81.3 reports target coverage before and after backfill for:

- `222m`
- `88m`
- `55m`

Coverage tracks shadow records, covered records, and archive candles.

## No-Live Guarantees

R81.3 payloads keep:

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
order_payload_created=false
network_allowed=false
secrets_shown=false
```

R81.3 does not bypass Markov, Miro Fish, funding, protective order, operator approval, or live execution gates.

## Smoke Commands

Dry-run capture/backfill:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-candle-capture --limit 20
```

Archive bridge status:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-candle-archive --limit 20
```

Resolver dry-run:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-shadow-resolve --limit 20
```

API dry-run when the local service is already running:

```text
curl -s -X POST http://127.0.0.1:8015/betrayal-shadow/candle-capture/backfill \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true,"write":false,"limit":20,"source_mode":"LOCAL_ONLY"}' \
  | jq '.status, .phase, .execution_mode, .source_mode, .candles_found, .candles_written'
```

## Next Phase Recommendation

Run Hammer Radar long enough for the runtime capture hook to populate `candle_archive/`, then rerun R81.1 resolver in dry-run mode. Only persist resolver output after reviewing target coverage and resolved sample quality. After enough resolved true inverse samples exist, proceed to R82 Markov Regime Gate.
