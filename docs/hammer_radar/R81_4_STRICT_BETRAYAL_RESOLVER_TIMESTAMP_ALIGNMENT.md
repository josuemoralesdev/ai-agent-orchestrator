# R81.4 Strict Betrayal Resolver Timestamp Alignment

## Purpose

R81.4 patches the betrayal shadow resolver so a shadow outcome can only resolve from candles that are valid for the original signal timestamp and forward evaluation window.

R81.4 is evidence-correctness work only. It does not place orders, call Binance live/trading endpoints, expose secrets, edit production env files, restart services, or make betrayal strategies live-ready.

## Why R81.4 Exists

R81.3 activated runtime candle capture and populated `logs/hammer_radar_forward/candle_archive/`. That allowed R81.1 to resolve shadow records, but smoke output exposed an unsafe mismatch:

```text
signal_timestamp: April 29-30, 2026
resolved_candle_timestamp: May 13, 2026
```

Those derived resolver records are not valid evidence. The original strategy stats and betrayal shadow records remain usable, but persisted `betrayal_shadow_resolutions.ndjson` rows that fail timestamp alignment must be ignored or quarantined in summaries.

## Strict Temporal Alignment Rules

For a candle to resolve a betrayal shadow record, it must satisfy all of these rules:

- candle symbol matches the shadow record symbol
- candle timeframe matches the shadow record timeframe
- candle timestamp is greater than or equal to `signal_timestamp`
- candle timestamp is less than or equal to the evaluation window end
- candidate candles are evaluated in chronological order
- no pre-signal candle may resolve a record
- no unrelated future candle may resolve a record

If candles exist for the symbol/timeframe but none pass the window check, the resolver returns no-data and includes:

```text
no_temporally_aligned_candles
```

## Evaluation Window

The default window is deterministic and conservative:

```text
evaluation_window_start = signal_timestamp
evaluation_window_end = signal_timestamp + max(3 * timeframe duration, 60 minutes)
```

This gives each timeframe a bounded forward replay window while preventing multi-week jumps for intraday records.

## Persisted Resolution Handling

R81.4 does not destructively delete existing resolution files. Instead, persisted resolution records are annotated with:

```text
evaluation_window_start
evaluation_window_end
temporal_alignment_ok
temporal_alignment_status
resolution_blockers
```

Persisted records with invalid alignment are excluded from merged shadow outcome records and therefore do not feed R81 true inverse validation sample counts.

R81 validation reports invalid persisted evidence through:

```text
true_inverse_summary.invalid_resolution_records
true_inverse_summary.temporally_invalid_resolved_records
true_inverse_summary.temporally_valid_resolved_records
```

## Conservative Tie Behavior

R81.4 preserves the R81.1 same-candle behavior. If a single OHLC candle could have hit both stop and take-profit, the resolver selects stop/loss first because intrabar order is unknowable.

## No-Live Guarantees

R81.4 keeps:

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

R81.4 does not bypass Markov, Miro Fish, funding, protective order, operator approval, or live execution gates.

## Smoke Commands

Resolver dry-run:

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

Resolution reader:

```text
curl -s http://127.0.0.1:8015/betrayal-shadow/resolutions?limit=20 | jq '
{
  summary,
  records: [.records[]? | {
    shadow_outcome_id,
    signal_timestamp,
    resolved_candle_timestamp,
    temporal_alignment_ok,
    temporal_alignment_status,
    resolution_status
  }]
}'
```

## Next Phase Recommendation

After R81.4, rerun resolver in dry-run mode first and inspect invalid/quarantined counts. Only persist new resolution output when target coverage and temporal alignment are clean. The next phase should either rebuild safe resolution evidence from temporally aligned archive candles or move to R82 Markov Regime Gate only after sufficient true inverse paper outcomes exist.
