# R96 Betrayal True Paper Tracking Scaffold

R96 turns current betrayal audit candidates into deterministic paper-trackable identities. It is a scaffold only: it declares signal IDs, hashes, future outcome schema, ledger paths, sample requirements, and next steps without fabricating outcomes or creating execution readiness.

R96 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, enable live execution, or create risk contracts.

## Why R96 Follows R95

R95 showed:

- normal lane remains support-pending
- betrayal lane has current audit opportunity
- betrayal evidence is still naive inverse audit evidence
- `overall_lane_class=BETRAYAL_LANE_NEEDS_TRUE_PAPER`

R96 is therefore the next non-executable step: create stable paper identities so a later phase can record actual inverse paper outcomes.

## Audit Evidence vs True Paper Evidence

R80 and R95 betrayal values are useful audit evidence, but they are not true paper evidence. R96 keeps every scaffolded candidate labeled:

```text
NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY
```

True paper evidence starts only after actual inverse entries, exits, stops, take-profits, and outcomes are recorded to the betrayal paper ledger.

## Paper Signal Identity

Direction/entry-mode candidates use:

```text
betrayal|BTCUSDT|4m|long_to_short|fib_650|direction_entry_mode
```

Aggregate candidates use:

```text
betrayal|BTCUSDT|222m|aggregate|timeframe_aggregate
```

Each identity also receives `betrayal_paper_signal_hash`, a SHA-256 hash of stable identity fields.

## Outcome Ledger

R96 declares the future ledger path:

```text
logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson
```

It declares this outcome schema without writing fake rows:

- `outcome_id`
- `betrayal_paper_signal_id`
- `candidate_hash`
- `symbol`
- `timeframe`
- `direction`
- `entry_mode`
- `source_signal_id`
- `source_timestamp`
- `paper_entry_price`
- `paper_stop_price`
- `paper_take_profit_price`
- `paper_exit_price`
- `paper_exit_reason`
- `paper_pnl_pct`
- `paper_result_win_loss`
- `max_adverse_excursion_pct`
- `max_favorable_excursion_pct`
- `created_at`
- `closed_at`
- `data_source`
- `review_only=true`
- `live_order_id=null`
- `real_order_placed=false`
- `order_payload_created=false`

## Minimum Requirements

Defaults:

- primary minimum true paper samples: `30`
- watchlist minimum true paper samples: `30`
- aggregate-only candidates require directional decomposition before paper maturity
- stop/take-profit data is required before promotion review
- Miro Fish / Markov equivalent review is required before any risk contract discussion

## Maturity

R96 candidates may reach:

- `PAPER_TRACKING_READY` for direction/entry-mode candidates
- `PAPER_IDENTITY_CREATED` for aggregate candidates needing decomposition
- `PAPER_EVIDENCE_INSUFFICIENT` after some outcomes exist but minimum samples are not met
- `PAPER_READY_FOR_REVIEW` only after minimum samples exist

Every R96 candidate remains:

- `true_paper_required=true`
- `live_ready=false`
- `executable=false`

## Surfaces

API:

```text
GET /live-arming/betrayal-true-paper-scaffold
POST /live-arming/betrayal-true-paper-scaffold/report
```

CLI:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-true-paper-scaffold
```

Optional scheduler task:

```text
betrayal_true_paper_scaffold
```

The task is available but not part of `DEFAULT_TASKS`. It runs dry-run/no-write by default.

## Smoke Commands

```bash
.venv/bin/python -m compileall src/app/hammer_radar
.venv/bin/python -m pytest tests/hammer_radar/test_betrayal_strategy_audit.py -q
.venv/bin/python -m pytest tests/hammer_radar/test_strategy_performance.py tests/hammer_radar/test_approval_api.py tests/hammer_radar/test_inspect.py tests/hammer_radar/test_paper_refresh_scheduler.py -q
.venv/bin/python -m pytest tests/hammer_radar -q
git diff --check
```

Local CLI inspection:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-true-paper-scaffold | sed -n '1,360p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward dual-lane-candidate-watch | sed -n '1,300p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-strategy-audit | sed -n '1,220p'
```

## Next Phase Recommendation

```text
R97 Betrayal Paper Outcome Ledger + First Tracking Loop
```

R97 should record real paper outcomes only. It should still remain non-executable and preserve all no-order, no-network, no-env-mutation guarantees unless a later explicit phase changes scope.
