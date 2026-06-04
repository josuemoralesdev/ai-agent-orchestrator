# R180 Multi-Lane Paper Capture Harvester

R180 adds a paper-only harvester across expanded BTCUSDT paper lanes.

It reads local lane controls and local signal/scan ledgers, separates paper lanes from existing tiny-live incumbents, captures fresh paper evidence into a new local ledger after exact confirmation, and reports which lane currently leads the evidence flow.

R180 does not write env/config files, write lane controls, write risk-contract config, call Binance, create order payloads, place orders, transfer, withdraw, enable live flags, disable the kill switch, set any lane `tiny_live`, or authorize live execution.

## Scope

R180 adds:

- `src/app/hammer_radar/operator/multi_lane_paper_capture_harvester.py`
- `multi-lane-paper-harvester` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson`
- `logs/hammer_radar_forward/multi_lane_paper_harvester_heartbeats.ndjson`

The harvester observes these BTCUSDT paper lanes from lane controls:

- `BTCUSDT|4m|long|ladder_close_50_618`
- `BTCUSDT|4m|short|ladder_close_50_618`
- `BTCUSDT|8m|long|ladder_close_50_618`
- `BTCUSDT|8m|short|ladder_close_50_618`
- `BTCUSDT|13m|short|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`

It also observes existing tiny-live incumbents as reference-only lanes:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

Reference observations do not count toward paper capture thresholds and do not imply live approval.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  multi-lane-paper-harvester \
  --latest-signals 1000 \
  --latest-scans 2000
```

Short smoke loop:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  multi-lane-paper-harvester \
  --latest-signals 1000 \
  --latest-scans 2000 \
  --max-iterations 2 \
  --sleep-seconds 1 \
  --iteration-timeout-seconds 30 \
  --heartbeat-every 1 \
  --run-harvester-loop \
  --record-harvest \
  --confirm-multi-lane-harvest "I CONFIRM MULTI LANE PAPER HARVESTING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  multi-lane-paper-harvester \
  --record-harvest \
  --confirm-multi-lane-harvest "wrong"
```

## Output

The command reports:

- `scope.paper_lanes`
- `scope.observed_tiny_live_lanes`
- `capture_summary.total_fresh_candidates`
- `capture_summary.total_captured`
- `capture_summary.fresh_by_lane`
- `capture_summary.stale_by_lane`
- `capture_summary.blocked_by_lane`
- `lane_capture_counts`
- `next_lane_candidate_recommendation`
- `harvest_status`
- `recommended_next_operator_move`
- `recommended_next_engineering_move`
- `safety`

`BTCUSDT|8m|short|ladder_close_50_618` counts include existing R157 capture records plus R180 captures. Other paper lane counts come from R180 capture records.

## Harvest Status Semantics

- `NO_FRESH_CANDIDATES`: no fresh paper candidates were found in the bounded local ledgers.
- `CAPTURED_ONE_OR_MORE_LANES`: at least one lane has fresh paper flow or captured evidence.
- `EIGHT_M_SHORT_STILL_LEAD`: 8m short remains tied or ahead in combined fresh flow and capture count.
- `NEW_LANE_CANDIDATE_EMERGED`: another lane has strictly overtaken 8m short in combined fresh flow and capture count.
- `THRESHOLD_MET_FOR_ONE_OR_MORE_LANES`: at least one paper lane has reached the configured fresh-capture threshold.
- `UNKNOWN_NEEDS_MANUAL_REVIEW`: defensive error/manual review state.

## Do Not Run Yet

- `live-connector-submit`
- any order endpoint
- global live flag arming
- kill switch disable
- set any lane `tiny_live`
- write risk contract config
- transfer
- withdraw

## Safety Boundary

R180 safety remains:

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

R181 should rank lanes using R180 records, compare 8m short against all other active paper lanes, and select the next best tiny-live candidate door. R181 remains non-executing and must not write config.
