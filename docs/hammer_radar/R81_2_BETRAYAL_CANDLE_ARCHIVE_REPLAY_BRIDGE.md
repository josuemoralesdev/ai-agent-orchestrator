# R81.2 Betrayal Candle Archive / Replay Bridge

## Purpose

R81.2 adds a local candle archive and replay bridge for betrayal shadow outcome validation. It gives the R81.1 resolver a deterministic place to find local OHLC candles so unresolved betrayal shadow records can become true inverse paper outcomes when data exists.

R81.2 does not fetch remote data, call Binance, place orders, expose secrets, edit env files, or make betrayal strategies live-ready.

## Why R81.2 Follows R81.1

R81.1 created the resolver and proved it stays safe, but smoke showed it could not resolve records because local candle archive data was missing:

```text
scanned_records=20
newly_resolved_records=0
no_data_records=20
222m resolved_records=0
88m resolved_records=0
```

R81.2 fixes the local replay data plumbing. If candle-shaped local NDJSON exists, it can be normalized into a replay archive. If data is absent, R81.2 reports missing coverage and does not invent candles.

## Archive Format

Archive path:

```text
logs/hammer_radar_forward/candle_archive/
```

Filename pattern:

```text
{symbol}_{timeframe}.ndjson
```

Each candle record contains:

```text
symbol
timeframe
open_time
timestamp
open
high
low
close
volume
source
archived_at
```

The archive bridge scans local candle-shaped NDJSON sources such as:

```text
candles.ndjson
market_candles.ndjson
price_candles.ndjson
paper_candles.ndjson
candle_archive/*.ndjson
```

Non-candle logs such as positions, signals, scanner summaries, and market intelligence metadata are not converted unless they contain complete OHLC candle fields.

## Dry-Run vs Write

Default behavior is dry-run/no-write.

Archive writes occur only when both conditions are true:

```text
dry_run=false
write=true
```

Writes are local only and dedupe candles by:

```text
symbol + timeframe + open_time
```

## Resolver Consumption

R81.1 resolver now reads the R81.2 candle archive when present. It still supports the previous flat local candle files. If neither source contains matching candles after the shadow signal timestamp, resolver behavior remains `SHADOW_NO_DATA`.

The no-fabrication rule is unchanged.

## Target Coverage

R81.2 reports target coverage for:

- `222m`
- `88m`
- `55m`

Coverage includes the number of shadow records, covered records, and available archive candles for each target timeframe.

## No-Live Guarantees

R81.2 payloads keep:

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

R81.2 does not bypass Markov, Miro Fish, funding, protective order, operator approval, or live execution gates.

## Smoke Commands

Dry-run archive scan:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-candle-archive --limit 20
```

Resolver dry-run after archive bridge:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-shadow-resolve --limit 20
```

R81 validation:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-inverse-validation
```

API smoke when the local service is already running:

```text
curl -s -X POST http://127.0.0.1:8015/betrayal-shadow/candle-archive/build \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true,"write":false,"limit":20}' \
  | jq '.status, .phase, .execution_mode, .candles_found, .candles_written, .target_coverage'
```

## Next Phase Recommendation

After local candle coverage exists and R81.1 resolves enough true inverse samples, rerun R81 validation and then add R82 Markov Regime Gate. Betrayal candidates should only remain under review when resolved inverse outcomes are repeatable in the active regime and still behind all live-readiness gates.
