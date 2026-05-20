# R98 Betrayal Paper Signal Detector / Outcome Capture Loop

R98 adds a local betrayal paper signal detector and capture loop. It reads R96 scaffold identities, checks R97 ledger status, scans local Hammer Radar paper archives, matches fresh source signals to betrayal direction/entry identities, prepares open tracking records, and captures closed paper outcomes through the R97 ledger validator.

R98 does not place orders, sign payloads, create executable exchange payloads, call Binance, check balances, modify env files, restart services, disable the kill switch, enable live execution, or create risk contracts.

## Why R98 Follows R97

R97 created the append-only ledger:

```text
logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson
```

R97 also confirmed the ledger was empty and that direction/entry identities were ready for tracking. R98 is the next paper-only step: find local source signals and convert only real observed paper evidence into prepared or closed betrayal paper records.

## Detection Sources

R98 uses existing local archive files:

```text
logs/hammer_radar_forward/signals.ndjson
logs/hammer_radar_forward/outcomes.ndjson
```

If no suitable local signal source exists, R98 returns `BETRAYAL_NO_FRESH_SIGNALS_FOUND`. It does not invent signals, scrape chat text, or use market/network calls.

## Identity Matching Rules

A source signal can match a direction/entry betrayal identity when:

- `symbol=BTCUSDT`
- timeframe matches
- source direction matches the scaffold original direction
- inverse source direction matches the scaffold betrayal direction
- entry mode matches
- audit scope is `direction_entry_mode`

Example:

```text
source: BTCUSDT 4m long fib_650
identity: betrayal|BTCUSDT|4m|long_to_short|fib_650|direction_entry_mode
paper direction: short
```

## Open Tracking vs Closed Outcome

Open tracking:

- prepared when a local source signal has entry, stop, and take-profit levels but no local outcome yet
- uses `paper_status=open`
- keeps exit, PnL, result, and closed timestamp null
- is not written to the R97 ledger because R97 validates closed outcomes

Closed outcome:

- prepared only when a matching local `OutcomeRecord` exists
- includes entry, stop, take-profit, exit, PnL, result, created timestamp, and closed timestamp
- writes only through R97 validation when `dry_run=false` and `write=true`

## Duplicate Prevention

R98 builds deterministic IDs:

```text
sha256(stable_json({
  betrayal_paper_signal_id,
  source_signal_id,
  source_timestamp,
  paper_status,
  closed_at
}))
```

If an `outcome_id` already exists in the R97 ledger, R98 returns `SIGNAL_REJECTED_DUPLICATE` and does not append a second row.

## Aggregate 222m Rule

The aggregate identity remains decomposition-required:

```text
betrayal|BTCUSDT|222m|aggregate|timeframe_aggregate
```

R98 does not force a direction. A 222m source can be rejected with `BETRAYAL_AGGREGATE_DECOMPOSITION_REQUIRED` unless a real directional entry-mode identity exists in the R96 scaffold.

## No Fake Outcomes Rule

R98 never creates closed outcomes without local outcome evidence. Open records are prepared-only. Closed records are captured only from existing local archive outcomes and only through R97 validation.

## Surfaces

API:

```text
GET /live-arming/betrayal-paper-signal-detector/status
GET /live-arming/betrayal-paper-signal-detector/detections
POST /live-arming/betrayal-paper-signal-detector/run
```

CLI:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-paper-signal-detector
```

Optional scheduler task:

```text
betrayal_paper_signal_detector
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
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-paper-signal-detector | sed -n '1,380p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-paper-outcomes | sed -n '1,260p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-true-paper-scaffold | sed -n '1,220p'
```

## Next Phase Recommendation

If local source signals exist:

```text
R99 Betrayal Outcome Capture Scheduler / Paper Maturity Snapshot
```

If no detector source can capture current signals:

```text
R99 Betrayal Directional Decomposition for 222m or detector source wiring
```
