# R97 Betrayal Paper Outcome Ledger + First Tracking Loop

R97 creates the local append-only true-paper outcome ledger for R96 betrayal identities. It records only explicitly supplied paper outcomes and summarizes maturity progress without fabricating evidence or creating any executable trading surface.

R97 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, enable live execution, or create risk contracts.

## Why R97 Follows R96

R96 created deterministic betrayal paper identities and declared the future ledger:

```text
logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson
```

It confirmed direction/entry-mode identities could start tracking, while the aggregate-only `222m` identity still requires directional decomposition. R97 is the first tracking loop that can read those identities, validate supplied outcomes against them, append valid local NDJSON rows, and compute early paper stats.

## Ledger Path

```text
logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson
```

Status/read paths never create this file. It is created only when `dry_run=false`, `write=true`, and a valid outcome object is supplied.

## Outcome Schema

- `outcome_id`
- `betrayal_paper_signal_id`
- `betrayal_paper_signal_hash`
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
- `execution_attempted=false`
- `network_allowed=false`
- `secrets_shown=false`

## Validation Rules

- `betrayal_paper_signal_id` must match an R96 scaffold identity.
- `betrayal_paper_signal_hash` must match the identity hash when supplied.
- `symbol` and `timeframe` must match the identity.
- Direction/entry-mode outcomes must match the scaffolded betrayal direction and entry mode.
- Aggregate-only identities cannot accept outcomes until decomposed into directional entry-mode identities.
- Paper entry, stop, take-profit, exit, and PnL values must be numeric.
- `paper_result_win_loss` must be `win` or `loss`.
- `review_only` must remain true.
- `live_order_id` must remain null.
- `real_order_placed`, `order_payload_created`, `execution_attempted`, `network_allowed`, and `secrets_shown` must remain false.

## Aggregate 222m Rule

The aggregate identity remains tracked but not outcome-writable:

```text
betrayal|BTCUSDT|222m|aggregate|timeframe_aggregate
```

It must be decomposed into a directional entry-mode identity before true-paper maturity can start. R97 does not force a direction.

## Minimum Sample Tracking

Each identity reports:

- outcome count
- required minimum samples, currently `30`
- progress percentage
- paper win rate when outcomes exist
- average, total, best, and worst paper PnL when outcomes exist
- `PAPER_EVIDENCE_EMPTY`, `PAPER_EVIDENCE_INSUFFICIENT`, or `PAPER_EVIDENCE_MIN_SAMPLE_REACHED`

All identities remain `live_ready=false` and `executable=false`.

## No Fake Outcomes Rule

R97 never writes synthetic results. Status reads, scheduler reads, and CLI reads only summarize existing ledger rows. Writes require an explicit local outcome object through API/CLI/test input.

## Surfaces

API:

```text
GET /live-arming/betrayal-paper-outcomes/status
GET /live-arming/betrayal-paper-outcomes
POST /live-arming/betrayal-paper-outcomes/record
```

CLI:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-paper-outcomes
```

Optional scheduler task:

```text
betrayal_paper_outcome_ledger
```

The task is available but not part of `DEFAULT_TASKS`. It is read/status only.

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
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-paper-outcomes | sed -n '1,360p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-true-paper-scaffold | sed -n '1,260p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward dual-lane-candidate-watch | sed -n '1,220p'
```

## Next Phase Recommendation

If the ledger is empty or under 30 samples, proceed with:

```text
R98 Betrayal Paper Signal Detector / Outcome Capture Loop
```

If a directional identity already has minimum samples, proceed with:

```text
R98 Betrayal Maturity Evaluator
```

R98 now scans local `signals.ndjson` and `outcomes.ndjson`, prepares open betrayal paper tracking records, and captures closed records through R97 validation only when explicitly run with `dry_run=false` and `write=true`.
