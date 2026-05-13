# R81 True Inverse Paper Outcome Validation

## Purpose

R81 converts betrayal strategy evidence from naive inverse audit math into true inverse paper outcome validation. It reads R80/R80.2 betrayal audit candidates and compares them with recorded betrayal shadow outcomes.

R81 does not place orders, enable live execution, call Binance, create signed payloads, edit env files, or make any betrayal strategy live-ready.

## Why R81 Follows R80.2

R80.2 separated timeframe aggregate betrayal candidates from direction/entry-mode candidates. That made the operator view clear:

- `222m` is a timeframe aggregate `BETRAYAL_PRIMARY_CANDIDATE`.
- `88m` is a timeframe aggregate `BETRAYAL_WATCHLIST`.
- Direction/entry-mode rows remain useful but are a separate audit layer.

R81 keeps those source candidates and asks the next question: did the hypothetical opposite-direction paper trades actually work as recorded shadow outcomes?

## Naive Audit vs True Inverse Validation

Naive inverse audit evidence mathematically flips historical aggregate metrics:

```text
betrayal_win_rate_pct = 100 - original_win_rate_pct
betrayal_avg_pnl_pct = -original_avg_pnl_pct
betrayal_total_pnl_pct = -original_total_pnl_pct
```

True inverse validation reads `betrayal_shadow_outcomes.ndjson` records and summarizes actual shadow outcomes:

- shadow win/loss/breakeven status
- shadow PnL
- resolved sample count
- unresolved or no-data count
- validation blockers

Naive inverse evidence and true inverse paper outcomes are reported separately.

R81.1 adds `betrayal_shadow_resolutions.ndjson` as an append-only resolver output. R81 validation reads those resolution records together with the base shadow records, with resolver records overriding matching `shadow_outcome_id` records for summary purposes.

## Source Targets

R81 sources candidates from:

```text
timeframe_aggregate_primary_candidates
timeframe_aggregate_watchlist_candidates
direction_entry_mode_primary_candidates
direction_entry_mode_watchlist_candidates
```

Current key aggregate targets:

- `222m` aggregate: primary validation target.
- `88m` aggregate: watchlist validation target.

## Betrayal Shadow Outcomes

R81 reuses the existing betrayal shadow outcome records produced by `betrayal-shadow-track` and read by `/betrayal-shadow/outcomes`.

Aggregate validations group shadow records by timeframe. Direction/entry-mode validations group by timeframe, original direction, and shadow direction when those fields exist in the shadow records.

If exact true inverse records do not exist yet, R81 reports `TRUE_INVERSE_NO_DATA`, `TRUE_INVERSE_VALIDATION_PENDING`, or `INSUFFICIENT_TRUE_INVERSE_OUTCOMES`. It does not infer success from R80/R80.2 naive metrics.

## Validation Statuses

R81 uses conservative statuses:

- `TRUE_INVERSE_VALIDATED_PRIMARY`
- `TRUE_INVERSE_VALIDATED_WATCHLIST`
- `TRUE_INVERSE_VALIDATION_PENDING`
- `INSUFFICIENT_TRUE_INVERSE_OUTCOMES`
- `TRUE_INVERSE_REJECTED`
- `TRUE_INVERSE_NO_DATA`

Validated statuses are still paper/shadow validation only. They are not live eligibility.

## Thresholds

Default validation thresholds:

- true inverse sample count >= `30`
- true inverse win rate >= `55%`
- true inverse average PnL > `0`
- true inverse total PnL > `0`
- unresolved/no-data records do not dominate records
- no safety blockers

If thresholds are not met, R81 returns pending, insufficient, or rejected status. It does not fake confidence.

## No-Live Guarantees

R81 payloads keep:

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

R81 does not bypass exact operator approval, live gates, funding gates, Markov, Miro Fish future gates, protected live review, or normal promotion review.

## Smoke Commands

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-inverse-validation

curl --max-time 5 -s http://127.0.0.1:8015/strategy-performance/betrayal-inverse-validation \
  | jq '.status, .phase, .execution_mode'

curl --max-time 5 -s http://127.0.0.1:8015/strategy-performance/betrayal-inverse-validation \
  | jq '.timeframe_aggregate_validations'
```

Run shadow tracking separately when more records are needed:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-shadow-track
```

## Next Phase Recommendation

R82 should add a Markov Regime Gate after true inverse validation. Betrayal candidates should only remain in consideration when inverse paper outcomes are repeatable in the current market regime. Even then, live eligibility must remain behind the normal promotion system, protected live gate review, exact operator approval, funding controls, and future Miro Fish gates.
