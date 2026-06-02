# R176 Capture Count Sync for BTCUSDT 8m Short

## Phase

R176 Capture Count Sync for BTCUSDT 8m Short

## Classification

- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk: MEDIUM

## Purpose

Sync the exact fresh capture count for `BTCUSDT|8m|short|ladder_close_50_618` from R157 records and determine whether the threshold of 10 fresh captures has been met.

## Required Behavior

- Read `logs/hammer_radar_forward/short_paper_evidence_capture.ndjson`.
- Count unique fresh captured signal IDs for the target lane.
- Report current count, required count, threshold status, latest capture ID, latest captured signal ID, and source ledger path.
- Reuse R157/R158 evidence helpers where practical.
- Keep the target lane paper.
- Produce a compact operator-facing summary suitable for R177/R158/R174 handoff.

## Non-Negotiables

- No config writes.
- No env writes or env mutation.
- No lane mode changes.
- No risk-contract config writes.
- No live execution.
- No Binance calls.
- No order, test-order, protective, transfer, or withdraw endpoints.
- No executable payloads.
- No signed requests.
- No secrets printed.
- No commits, merges, tags, or deploys.

## Expected CLI Shape

Suggested command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-capture-count-sync \
  --lane-key "BTCUSDT|8m|short|ladder_close_50_618"
```

## Expected Output Fields

- `status`
- `generated_at`
- `target_family`
- `fresh_capture_count`
- `required_fresh_capture_count`
- `threshold_met`
- `latest_capture_id`
- `latest_captured_signal_id`
- `recommended_next_operator_move`
- `recommended_next_engineering_move`
- `do_not_run_yet`
- `safety`
- `source_surfaces_used`

## Safety Object

Must include:

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
- `full_api_key_shown=false`
- `full_api_secret_shown=false`
- `global_live_flags_changed=false`
- `kill_switch_disabled=false`
- `paper_live_separation_intact=true`

## Validation

- Run py_compile for any new module and `inspect.py`.
- Run focused tests for the new capture-count sync.
- Run related R157/R158 tests.
- Run `tests/hammer_radar` if scope warrants.
