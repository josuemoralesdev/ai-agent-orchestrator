# R144 Signal-to-Watcher Eligibility Trace

R144 explains why visible `BTCUSDT` signals in `signals.ndjson` do or do not become R142 watcher-eligible paper proof candidates.

This is a trace/audit phase only. It does not change router behavior, signal eligibility, lane config, env flags, live gates, or execution behavior.

## Why R144 Exists

R143 recorded tiny-live lane unlock intent for:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

The unlock contract state is `UNLOCKED_WAITING_FOR_CONDITIONS`, but R142 can still time out when:

- `fresh_routed_count = 0`
- `paper_eligible_decisions_count = 0`
- visible signals exist in `signals.ndjson`
- visible signal records do not expose `entry_mode`
- the paper scan surface shows high-priority BTC watches that do not map to watched lane keys

R144 answers the operator question: why did this visible signal not become a watcher-eligible lane candidate?

## Visible Signal vs Watcher-Eligible Candidate

A visible signal is a local archived signal row with fields such as `symbol`, `timeframe`, `direction`, `timestamp`, and strategy context.

A watcher-eligible candidate must match the watched lane key exactly:

```text
symbol|timeframe|direction|entry_mode
```

For the current R142/R143 lanes, `BTCUSDT|13m|long` is not enough. The candidate must also carry `entry_mode=ladder_close_50_618`.

## Trace Surfaces

R144 reads:

- `logs/hammer_radar_forward/signals.ndjson`
- `logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson`
- `logs/hammer_radar_forward/fresh_candidate_paper_proof_capture_loop.ndjson`
- R143 unlock-contract status
- R123 fresh router preview
- R129 paper executor integration preview

R144 writes only when explicitly confirmed:

- `logs/hammer_radar_forward/signal_to_watcher_eligibility_traces.ndjson`

## Gap Classifications

R144 classifies each traced signal as one of:

- `SIGNAL_MATCHES_WATCHED_LANE_AND_ELIGIBLE`
- `SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING`
- `SIGNAL_MATCHES_TIMEFRAME_DIRECTION_BUT_ENTRY_MODE_MISMATCH`
- `SIGNAL_TIMEFRAME_NOT_WATCHED`
- `SIGNAL_DIRECTION_NOT_WATCHED`
- `SIGNAL_SYMBOL_NOT_WATCHED`
- `SIGNAL_STALE_BY_WATCHER_RULES`
- `SIGNAL_NOT_FOUND_IN_PAPER_SCAN`
- `SIGNAL_FOUND_IN_SCAN_BUT_NOT_ROUTED`
- `SIGNAL_ROUTED_BUT_NOT_PAPER_ELIGIBLE`
- `SIGNAL_BLOCKED_BY_PAPER_EXECUTOR`
- `SIGNAL_BLOCKED_BY_UNLOCK_CONTRACT_ABSENCE`
- `SIGNAL_BLOCKED_BY_LANE_MODE`
- `SIGNAL_BLOCKED_BY_UNKNOWN_REASON`

The expected likely R144 finding is that BTCUSDT 13m/44m long signals are visible, but `entry_mode` is missing from the archived signal row, so they do not exactly match the watched lane keys.

## Commands

Preview all unlocked lanes:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-to-watcher-eligibility-trace \
  --trace-all-unlocked-lanes
```

Trace one signal:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-to-watcher-eligibility-trace \
  --trace-all-unlocked-lanes \
  --signal-id "BTCUSDT|44m|long|2026-05-28T12:39:59.999000+00:00"
```

Record a trace:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-to-watcher-eligibility-trace \
  --trace-all-unlocked-lanes \
  --record-trace \
  --confirm-trace "I CONFIRM SIGNAL TO WATCHER TRACE RECORDING ONLY; NO ORDER; NO BINANCE CALL."
```

The confirmation records the trace only. It does not authorize order placement, Binance calls, live execution, lane config mutation, env mutation, or global flag mutation.

## How This Prepares R145

If R144 confirms `SIGNAL_MATCHES_WATCHED_LANE_BUT_ENTRY_MODE_MISSING`, R145 should add an entry-mode derivation bridge or paper scan candidate normalization path so eligible BTCUSDT 13m/44m signals can become lane-key-addressable watcher candidates without changing live execution boundaries.
