#!/usr/bin/env bash
set -euo pipefail

cat <<'PLAN'
R299 PRINT ONLY - real-candidate timer observation certificate plan

This script prints commands only. It does not execute sudo, systemctl, curl,
order submission, install, copy, move, delete, or cleanup commands.

1. Timer health check
   curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/timer-health | jq '{
     event_type,
     status,
     timer_active,
     timer_loaded,
     recent_tick_seen,
     recent_tick_count,
     final_command_available,
     submit_allowed,
     real_order_forbidden,
     safety
   }'

2. Scheduler status check
   curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq '{
     event_type,
     status,
     current_fresh_candidate_exists,
     current_candidate_lane_key,
     latest_scheduler_status,
     latest_trigger_loop_status,
     final_command_available,
     submit_allowed,
     real_order_forbidden,
     safety
   }'

3. R298 bridge status check
   curl -sS http://127.0.0.1:8015/tiny-live/real-candidate-dry-run-trigger-bridge/status | jq '{
     event_type,
     status,
     current_real_candidate_exists,
     current_real_candidate_lane_key,
     candidate_matches_requested_lane,
     test_only,
     fake_candidate_used,
     simulated_dry_run_trigger_recorded,
     final_command_available,
     submit_allowed,
     real_order_forbidden,
     safety
   }'

4. R299 CLI certificate command
   PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
     --log-dir logs/hammer_radar_forward \
     tiny-live-real-candidate-timer-observation-certificate \
     --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
     --operator-id local_operator \
     --reason "R299 real-candidate timer observation certificate; no fake candidate; no submit; no order." \
     --record-real-candidate-timer-observation-certificate \
     | jq '{
       event_type,
       status,
       requested_lane_key,
       timer_health_status,
       timer_active,
       timer_loaded,
       recent_tick_seen,
       recent_tick_count,
       scheduler_latest_status,
       scheduler_latest_trigger_loop_status,
       r298_bridge_status,
       current_real_candidate_exists,
       test_only,
       fake_candidate_used,
       final_command_available,
       submit_allowed,
       real_order_forbidden,
       executable_payload_created,
       order_payload_created,
       order_placed,
       binance_order_endpoint_called,
       binance_test_order_endpoint_called,
       blockers,
       safety
     }'

5. R299 API status command
   curl -sS http://127.0.0.1:8015/tiny-live/real-candidate-timer-observation-certificate/status | jq '{
     event_type,
     status,
     real_candidate_timer_observation_certificate_panel,
     final_command_available,
     submit_allowed,
     real_order_forbidden,
     safety
   }'

6. Final console check
   curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '{
     status,
     real_candidate_timer_observation_certificate_panel,
     real_candidate_dry_run_trigger_bridge_panel,
     final_live_submit_command_packet,
     recommended_next_operator_move,
     safety
   }'

7. Safety grep
   grep -R "\"order_placed\": true\|\"binance_order_endpoint_called\": true\|\"binance_test_order_endpoint_called\": true\|\"submit_attempted\": true\|\"real_order_placed\": true\|\"final_command_available\": true\|\"submit_allowed\": true\|\"executable_payload_created\": true\|\"secrets_shown\": true\|\"live_execution_enabled\": true\|\"allow_live_orders\": true\|\"fake_candidate_used\": true" -n \
     logs/hammer_radar_forward/tiny_live*.ndjson \
     logs/hammer_radar_forward/*autonomous*.ndjson \
     logs/hammer_radar_forward/*binance*.ndjson \
     2>/dev/null || true

8. Cleanup guidance
   R299 only writes logs/hammer_radar_forward/tiny_live_real_candidate_timer_observation_certificate.ndjson
   when --record-real-candidate-timer-observation-certificate is explicitly used.
   Review runtime log dirt before committing; do not remove logs until the operator confirms.
PLAN
