# R100 Betrayal Source Signal Emitter

R100 adds a local review-only source signal emitter for the betrayal paper detector. It emits explicit-entry betrayal paper signal rows into:

```text
logs/hammer_radar_forward/betrayal_paper_signals.ndjson
```

R100 does not write the R97 outcome ledger, fabricate closed outcomes, place orders, sign payloads, call Binance, check balances, modify env files, restart services, enable live execution, or create risk contracts.

## Why R100 Follows R99

R99 found the detector source gap:

- `signals.ndjson` exists but lacks explicit `entry_mode`
- `outcomes.ndjson` has explicit `entry_mode` and is usable for historical closed evidence
- R98 is safe but currently returns `BETRAYAL_NO_FRESH_SIGNALS_FOUND`
- aggregate `222m` remains decomposition-required

R100 builds the missing local pipe between explicit-entry paper history and the future R98 detector source. It labels these rows as historical replay unless a future source proves true freshness.

## Source Inventory Problem

Primary source:

```text
logs/hammer_radar_forward/outcomes.ndjson
```

R100 reads local outcomes only when they contain:

- symbol
- timeframe
- original direction
- explicit entry mode
- source signal ID
- source timestamp
- entry price

For stop/take-profit, R100 requires the linked local `signals.ndjson` row to provide deterministic hammer high/low geometry. If stop or take-profit cannot be derived from existing local data, R100 skips the row and reports `missing_price_fields_count`.

## Emitted Signal Schema

Each emitted row includes:

- `emitted_signal_id`
- `betrayal_paper_signal_id`
- `betrayal_paper_signal_hash`
- `source_signal_id`
- `source_record_id`
- `source_timestamp`
- `emitted_at`
- `symbol`
- `timeframe`
- `original_direction`
- `betrayal_direction`
- `direction`
- `entry_mode`
- `paper_entry_price`
- `paper_stop_price`
- `paper_take_profit_price`
- `signal_freshness`
- `data_source`
- `paper_signal_status`
- `review_only=true`
- `live_ready=false`
- `executable=false`
- `real_order_placed=false`
- `order_payload_created=false`
- `execution_attempted=false`
- `network_allowed=false`
- `secrets_shown=false`

## Historical Replay vs Fresh Current

Historical replay rows use:

```text
signal_freshness=historical_replay
data_source=outcomes_replay_for_detector_wiring
paper_signal_status=historical_replay
is_fresh_current_signal=false
eligible_for_live=false
```

They are detector plumbing records. They are not current market signals and do not imply live readiness.

## Matching Rules

For each R96 direction/entry identity:

- source symbol must match
- source timeframe must match
- source `entry_mode` must match
- source original direction must match identity original direction
- emitted `direction` must be the scaffold betrayal direction

Example:

```text
source: BTCUSDT 4m long fib_650
identity: betrayal|BTCUSDT|4m|long_to_short|fib_650|direction_entry_mode
emitted direction: short
```

## Duplicate Prevention

R100 builds deterministic IDs:

```text
sha256(stable_json({
  betrayal_paper_signal_id,
  source_signal_id,
  source_timestamp,
  entry_mode,
  signal_freshness
}))
```

If `emitted_signal_id` already exists in `betrayal_paper_signals.ndjson`, R100 skips the duplicate and reports `BETRAYAL_DUPLICATE_EMISSION_SKIPPED`.

## Aggregate 222m Rule

Aggregate identities such as:

```text
betrayal|BTCUSDT|222m|aggregate|timeframe_aggregate
```

are skipped unless a real directional entry-mode identity exists. R100 does not force a direction or create fake decomposition. Skips are reported as `BETRAYAL_AGGREGATE_SKIPPED_DECOMPOSITION_REQUIRED`.

## No Fake Outcomes Rule

R100 emits paper signal rows only. It never appends to:

```text
logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson
```

It does not create closed outcome rows or invent stop/take-profit prices.

## Surfaces

API:

```text
GET /live-arming/betrayal-source-signal-emitter/status
GET /live-arming/betrayal-source-signal-emitter/signals
POST /live-arming/betrayal-source-signal-emitter/run
```

CLI:

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-source-signal-emitter
```

Optional scheduler task:

```text
betrayal_source_signal_emitter
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
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-source-signal-emitter | sed -n '1,400p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-detector-source-wiring | sed -n '1,260p'
.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward betrayal-paper-signal-detector | sed -n '1,220p'
```

## Next Phase Recommendation

Proceed with:

```text
R101 Wire R98 Detector to R100 Emitted Signal Source
```

R101 should make the R98 detector consume `betrayal_paper_signals.ndjson` while preserving dry-run/no-write defaults and all no-order/no-network/no-env-change guarantees.
