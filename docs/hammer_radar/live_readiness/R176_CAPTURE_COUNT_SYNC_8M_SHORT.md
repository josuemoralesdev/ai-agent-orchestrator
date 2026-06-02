# R176 Capture Count Sync and Always-On Watcher Guard for BTCUSDT 8m Short

R176 adds a local-only sync surface for `BTCUSDT|8m|short|ladder_close_50_618`.

It reads R157 capture records and R157 heartbeat records, reports the current unique fresh capture count, classifies watcher heartbeat recency, emits a safe tmux restart command, and optionally appends a sync record after exact confirmation.

R176 does not write env/config files, write lane controls, write risk-contract config, call Binance, create payloads, place orders, transfer, withdraw, enable live flags, disable the kill switch, set the short lane `tiny_live`, or authorize live execution.

## Scope

R176 adds:

- `src/app/hammer_radar/operator/capture_count_sync_8m_short.py`
- `capture-count-sync-8m-short` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson` as an append-only sync ledger after exact confirmation

The sync composes existing local surfaces:

- fresh paper evidence from `short_paper_evidence_capture.ndjson`
- watcher recency from `short_paper_evidence_capture_heartbeats.ndjson`
- target family mode from lane controls through the existing short strategy target helper

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-count-sync-8m-short
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-count-sync-8m-short \
  --record-sync \
  --confirm-capture-count-sync "wrong"
```

Record with exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-count-sync-8m-short \
  --record-sync \
  --confirm-capture-count-sync "I CONFIRM CAPTURE COUNT SYNC RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Output

The command reports:

- `capture_count.fresh_capture_count`
- `capture_count.required_fresh_capture_count=10`
- `capture_count.unique_captured_signal_ids`
- `capture_count.latest_captured_signal_id`
- `watcher_status.latest_heartbeat_found`
- `watcher_status.heartbeat_age_seconds`
- `watcher_status.watcher_likely_running`
- `watcher_status.watcher_stale`
- `safe_watcher_commands.tmux_session=r176-8m-short-capture`
- `threshold_status`
- whether R158 should be rerun through the R177 recheck path

## Threshold Semantics

- `CAPTURE_THRESHOLD_MET`: unique captured signal IDs are at least 10.
- `CAPTURE_THRESHOLD_NOT_MET`: watcher appears active but the count is still below 10.
- `CAPTURE_WATCHER_INACTIVE`: no usable active heartbeat was found.
- `CAPTURE_WATCHER_STALE`: latest heartbeat is older than the stale threshold.
- `UNKNOWN_NEEDS_MANUAL_REVIEW`: defensive error/manual review state.

When the threshold is met, R176 recommends `RUN_R177_EVIDENCE_THRESHOLD_RECHECK`. R177 should rerun R158 evidence readiness and decide if risk-contract apply review can proceed, still without live execution or config writes by default.

## Do Not Run Yet

- `live-connector-submit`
- any order endpoint
- global live flag arming
- kill switch disable
- set short lane `tiny_live`
- write risk contract config
- transfer
- withdraw

## Safety Boundary

R176 safety remains:

- `env_written=false`
- `env_mutated=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `signed_readonly_request_created=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `transfer_endpoint_called=false`
- `withdraw_endpoint_called=false`
- `secrets_shown=false`
- `global_live_flags_changed=false`
- `kill_switch_disabled=false`
- `paper_live_separation_intact=true`
