#!/usr/bin/env bash
set -euo pipefail

cat <<'PLAN'
R294 PRINT ONLY - dry-run lane arming rehearsal plan

This script prints commands only. It does not run systemctl, curl, sudo, order
commands, install commands, copy/move/delete commands, or any Binance request.

1. Timer health check

PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-timer-health \
  | jq '{
    status,
    timer_active,
    recent_tick_seen,
    documentation_warning_seen,
    installed_unit_refresh_required,
    final_command_available,
    submit_allowed,
    real_order_forbidden,
    safety
  }'

2. R294 status check

PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-dry-run-lane-arming-rehearsal \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R294 dry-run lane arming rehearsal only; no submit; no order." \
  | jq '{
    event_type,
    status,
    requested_lane_key,
    timer_health_status,
    timer_active,
    recent_tick_seen,
    current_fresh_candidate_exists,
    current_candidate_lane_key,
    current_candidate_matches_armed_lane,
    simulated_trigger_recorded,
    final_command_available,
    submit_allowed,
    real_order_forbidden,
    executable_payload_created,
    order_payload_created,
    order_placed,
    binance_order_endpoint_called,
    binance_test_order_endpoint_called,
    safety
  }'

3. Safe CLI record rehearsal command

PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-dry-run-lane-arming-rehearsal \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R294 dry-run lane arming rehearsal only; no submit; no order." \
  --record-dry-run-lane-arming-rehearsal

4. Existing dry-run arming cleanup command, if operator wants OFF state

PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-dry-run-disarm-lane \
  --operator-id local_operator \
  --reason "R294 cleanup; return autonomous dry-run arming to OFF." \
  --confirm-dry-run-autonomous-disarm "I CONFIRM AUTONOMOUS DRY-RUN DISARM; RETURN TO OFF."

5. R294 API status check

curl -sS http://127.0.0.1:8015/tiny-live/dry-run-lane-arming-rehearsal/status \
  | jq '{
    event_type,
    status,
    dry_run_lane_arming_rehearsal_panel,
    final_command_available,
    submit_allowed,
    real_order_forbidden,
    safety
  }'

6. Safety grep

grep -R "\"order_placed\": true\|\"binance_order_endpoint_called\": true\|\"binance_test_order_endpoint_called\": true\|\"submit_attempted\": true\|\"real_order_placed\": true\|\"final_command_available\": true\|\"submit_allowed\": true\|\"executable_payload_created\": true\|\"secrets_shown\": true\|\"live_execution_enabled\": true\|\"allow_live_orders\": true" -n \
  logs/hammer_radar_forward/tiny_live*.ndjson \
  logs/hammer_radar_forward/*autonomous*.ndjson \
  logs/hammer_radar_forward/*binance*.ndjson \
  2>/dev/null || true

7. Rollback / cleanup guidance

- R294 writes only logs/hammer_radar_forward/tiny_live_dry_run_lane_arming_rehearsal.ndjson when --record-dry-run-lane-arming-rehearsal is used.
- Do not delete runtime logs during an active audit. If cleanup is required, archive the R294 ledger manually outside Codex after review.
- To return dry-run arming to OFF, run the disarm command printed above.
- Do not run live submit, final submit, Binance order, Binance test-order, leverage mutation, or margin mutation commands for R294.
PLAN
