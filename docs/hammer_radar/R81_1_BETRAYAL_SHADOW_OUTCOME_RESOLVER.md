# R81.1 Betrayal Shadow Outcome Resolver

## Purpose

R81.1 resolves betrayal shadow records into true inverse paper outcomes when local archived candle data is available. It turns unresolved shadow records into auditable `SHADOW_WIN` or `SHADOW_LOSS` records with paper PnL, without placing orders or fetching external data.

R81.1 is paper/shadow/outcome resolution only. It does not make betrayal strategies live-ready.

## Why R81.1 Follows R81

R81 added the true inverse validation surface, but the initial smoke showed:

```text
total_shadow_records=543
resolved_shadow_records=0
```

That means R81 could identify validation targets such as `222m` and `88m`, but it had no resolved true inverse samples to evaluate. R81.1 adds the missing local resolver layer.

## Resolver Semantics

The resolver reads existing `betrayal_shadow_outcomes.ndjson` records and attempts to resolve records with unresolved/open/no-data status.

For each record it uses:

- `shadow_direction`
- `shadow_entry`
- `shadow_stop`
- `shadow_take_profit`
- `signal_timestamp`
- `symbol`
- `timeframe`

It then scans local candle files when present:

```text
candles.ndjson
market_candles.ndjson
price_candles.ndjson
paper_candles.ndjson
```

No network fetch is allowed. If local candles are missing, the record stays `SHADOW_NO_DATA`.

R81.2 adds a local candle archive bridge. When `candle_archive/*.ndjson` records are present, the resolver reads those archive candles before falling back to flat local candle files.

## Resolution Rules

- If take-profit is hit first: `SHADOW_WIN`
- If stop is hit first: `SHADOW_LOSS`
- If neither level is hit in available candles: `SHADOW_OPEN`
- If candle data is missing: `SHADOW_NO_DATA`
- If required record fields are missing: `SHADOW_UNRESOLVED`

The resolver computes `shadow_pnl_pct` and `true_inverse_pnl_pct` from the shadow direction, entry, and exit price.

## Conservative Tie Behavior

If a single candle high/low can hit both stop and take-profit, R81.1 chooses stop/loss first. Intrabar order is unknowable from OHLC data, so the resolver uses the same conservative behavior as paper position handling.

## Dry-Run vs Write

Default behavior is dry-run/no-write.

Resolver output is only persisted when both are true:

```text
dry_run=false
write=true
```

Resolved records are appended to:

```text
betrayal_shadow_resolutions.ndjson
```

The original `betrayal_shadow_outcomes.ndjson` file is not destructively rewritten. Existing resolved records are not duplicated.

## R81 Consumption

R81 validation now reads base betrayal shadow records plus resolver output. Resolver records override matching shadow records by `shadow_outcome_id` for summary purposes.

When R81.1 resolves records, R81 can report higher:

```text
true_inverse_summary.resolved_shadow_records
true_inverse_sample_count
```

for affected candidates such as `222m` and `88m`.

## No-Live Guarantees

R81.1 payloads keep:

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

R81.1 does not bypass Markov, Miro Fish, funding, protective order, operator approval, or live execution gates.

## Smoke Commands

Dry-run resolver smoke:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-shadow-resolve --limit 20
```

R81 validation after resolver output exists:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-inverse-validation
```

API dry-run smoke when the local service is already running:

```text
curl -s -X POST http://127.0.0.1:8015/betrayal-shadow/resolve \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true,"write":false,"limit":20}' \
  | jq '.status, .phase, .execution_mode, .scanned_records, .newly_resolved_records, .no_data_records'
```

## Next Phase Recommendation

After enough true inverse outcomes are resolved, the next phase should evaluate regime context with the R82 Markov Regime Gate. Betrayal candidates should only remain under consideration when resolved inverse outcomes are repeatable in the active regime, and still behind normal promotion, operator approval, funding, protective order, and future Miro Fish gates.
