# R99 Betrayal Detector Source Wiring + 222m Decomposition

R99 diagnoses why the R98 betrayal paper signal detector found no fresh signals and reviews aggregate betrayal candidates for real direction/entry decomposition evidence. It remains review-only.

R99 does not create signals, fabricate paper outcomes, place orders, sign payloads, call Binance, check balances, modify env files, restart services, enable live execution, or create risk contracts.

## Why R99 Follows R98

R98 added a safe detector and capture loop, but current local execution returned:

```text
BETRAYAL_NO_FRESH_SIGNALS_FOUND
detected_signal_count=0
matched_signal_count=0
captured_outcome_count=0
```

R99 answers whether the issue is missing local source records, incomplete fields, or lack of directional decomposition for aggregate candidates such as `222m`.

## Detector Source Inventory

R99 inspects local files under:

```text
logs/hammer_radar_forward
```

Checked sources include:

- `signals.ndjson`
- `outcomes.ndjson`
- `paper_executions.ndjson`
- `trade_tickets.ndjson`
- `positions.ndjson`
- `position_events.ndjson`
- `betrayal_shadow_outcomes.ndjson`
- `betrayal_shadow_resolutions.ndjson`
- `paper_refresh_runs.ndjson`

Missing and malformed files are reported without crashing.

## Source Mapping Rules

For detector use, a source needs enough fields to map into R98:

- symbol
- timeframe
- normal source direction
- entry mode
- timestamp/source timestamp
- source signal ID
- entry price when possible
- stop and take-profit when possible for open tracking
- exit and PnL only for closed outcomes

The detector maps normal direction into betrayal direction by inversion. Example:

```text
normal long -> betrayal short
normal short -> betrayal long
```

## Why R98 Found No Fresh Signals

R98 requires explicit entry-mode source records. If `signals.ndjson` exists but records do not carry an `entry_mode` field or a signal ID containing an entry mode such as `fib_650` or `fib_618`, R98 treats them as non-detector-qualified historical/audit records.

R99 reports that gap instead of inventing signals.

## 222m Aggregate Decomposition

The aggregate identity remains:

```text
betrayal|BTCUSDT|222m|aggregate|timeframe_aggregate
```

R99 reviews betrayal audit direction/entry rows for `222m`. It proposes directional identities only when real local audit evidence already contains:

- original direction
- betrayal direction
- entry mode
- sample count
- naive inverse win rate
- naive inverse total PnL

Proposed identities use:

```text
betrayal|BTCUSDT|222m|<original>_to_<betrayal>|<entry_mode>|direction_entry_mode
```

They remain:

- `review_only=true`
- `live_ready=false`
- `executable=false`
- `requires_true_paper_tracking=true`

## No Forced Aggregate Conversion

If no eligible directional evidence exists, R99 returns:

```text
AGGREGATE_DECOMPOSITION_NOT_AVAILABLE
```

It also reports missing fields and recommends either a source signal emitter or a directional audit expansion phase.

## Surfaces

API:

```text
GET /live-arming/betrayal-detector-source-wiring
POST /live-arming/betrayal-detector-source-wiring/report
```

CLI:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-detector-source-wiring
```

Optional scheduler task:

```text
betrayal_detector_source_wiring
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
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-detector-source-wiring | sed -n '1,380p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-paper-signal-detector | sed -n '1,260p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-paper-outcomes | sed -n '1,220p'
```

## Next Phase Recommendation

If directional decomposition is available, proceed with:

```text
R100 Betrayal Outcome Capture Scheduler / Paper Maturity Snapshot
```

If no usable detector source or directional decomposition is available, proceed with:

```text
R100 Source Signal Emitter for Betrayal Paper Detector
```

or:

```text
R100 222m Directional Audit Expansion
```

R100 now implements the source signal emitter path by creating local review-only `betrayal_paper_signals.ndjson` rows from explicit-entry outcome replay evidence. It does not write the R97 outcome ledger or convert aggregate identities into forced directional signals.
