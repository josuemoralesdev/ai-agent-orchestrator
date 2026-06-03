# R179 Capture Watcher Supervisor for BTCUSDT 8m Short

R179 adds a paper-only supervisor for `BTCUSDT|8m|short|ladder_close_50_618`.

It reads R157 capture records, R157 heartbeat records, and R176 capture-count logic to decide whether the watcher should keep running, be restarted after a capture exit, be restarted after stale/missing heartbeat, or stop supervising after the 10 fresh-capture threshold is met.

R179 does not write env/config files, write lane controls, write risk-contract config, call Binance, create payloads, place orders, transfer, withdraw, enable live flags, disable the kill switch, set the short lane `tiny_live`, or authorize live execution.

## Scope

R179 adds:

- `src/app/hammer_radar/operator/capture_watcher_supervisor_8m_short.py`
- `capture-watcher-supervisor-8m-short` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/capture_watcher_supervisor_8m_short.ndjson` as an append-only supervisor ledger after exact confirmation

The supervisor reuses:

- R157 `short-paper-evidence-capture-loop`
- R176 capture count and heartbeat helpers
- the existing target family lane-mode helper

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-watcher-supervisor-8m-short
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-watcher-supervisor-8m-short \
  --record-supervisor \
  --confirm-capture-watcher-supervisor "wrong"
```

Record with exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-watcher-supervisor-8m-short \
  --record-supervisor \
  --confirm-capture-watcher-supervisor "I CONFIRM CAPTURE WATCHER SUPERVISOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Bounded loop preview without restarts:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-watcher-supervisor-8m-short \
  --run-supervisor-loop \
  --max-supervisor-iterations 60 \
  --sleep-seconds 60
```

The loop does not restart the paper watcher unless `--allow-paper-watcher-restart` is present.

## Supervisor Decisions

- `THRESHOLD_MET_STOP_SUPERVISING`: fresh captures are at least 10; run R177 next.
- `WATCHER_RUNNING_KEEP_WAITING`: watcher heartbeat is recent and non-terminal; keep waiting.
- `WATCHER_EXITED_AFTER_CAPTURE_RESTART_RECOMMENDED`: latest heartbeat is terminal after a capture; restart the paper watcher.
- `WATCHER_STALE_RESTART_RECOMMENDED`: latest heartbeat is stale; restart the paper watcher.
- `WATCHER_NOT_FOUND_RESTART_RECOMMENDED`: no heartbeat exists; start the paper watcher.
- `UNKNOWN_NEEDS_MANUAL_REVIEW`: inspect capture and heartbeat ledgers manually before restarting.

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

R179 safety remains:

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

## Next Phase

R180 should preview a long-running supervisor service shape using systemd or tmux, with no install by default, no config writes, no live execution, and no Binance calls.
