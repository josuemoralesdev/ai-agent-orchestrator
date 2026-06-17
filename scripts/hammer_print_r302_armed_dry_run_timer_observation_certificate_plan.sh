#!/usr/bin/env bash
set -euo pipefail

cat <<'PLAN'
R302 PRINT ONLY - armed dry-run timer observation certificate plan

This script prints commands only. It does not execute curl, service actions, installs, file moves, file deletes, arming, disarming, orders, submits, or Binance calls.

1. R301 post-arm certificate check:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-operator-dry-run-arming-post-arm-certificate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R301 post-arm verification before R302; no Codex arming; no submit; no order."

2. R302 API status check:
curl -sS 'http://127.0.0.1:8015/tiny-live/armed-dry-run-timer-observation-certificate/status?lane_key=BTCUSDT%7C44m%7Clong%7Cladder_close_50_618' \
  | jq '{event_type,status,requested_lane_key,exact_lane_auto_armed,any_lane_auto_armed,armed_lane_key,timer_active,recent_tick_seen,recent_tick_count,scheduler_latest_status,scheduler_latest_trigger_loop_status,current_real_candidate_exists,current_real_candidate_lane_key,candidate_matches_requested_lane,final_command_available,submit_allowed,real_order_forbidden,blockers}'

3. R302 CLI certificate command:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-armed-dry-run-timer-observation-certificate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R302 armed dry-run timer observation certificate; no submit; no order." \
  --record-armed-dry-run-timer-observation-certificate

4. Scheduler status command:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-timer-health

5. Final console panel check:
curl -sS http://127.0.0.1:8015/tiny-live/final-console \
  | jq '.armed_dry_run_timer_observation_certificate_panel'

6. Manual operator disarm rollback command:
DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER: PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-dry-run-disarm-lane \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "Manual operator rollback/disarm dry-run arming after R302 observation; no submit; no order." \
  --confirm-dry-run-autonomous-disarm "I CONFIRM AUTONOMOUS DRY-RUN DISARM; RETURN TO OFF."

7. Safety grep:
grep -R "\"order_placed\": true\|\"binance_order_endpoint_called\": true\|\"binance_test_order_endpoint_called\": true\|\"submit_allowed\": true\|\"final_command_available\": true\|\"executable_payload_created\": true\|\"codex_arming_performed\": true\|\"codex_config_mutation_performed\": true\|\"live_execution_enabled\": true\|\"allow_live_orders\": true\|\"fake_candidate_used\": true" -n \
  logs/hammer_radar_forward/tiny_live_armed_dry_run_timer_observation_certificate.ndjson \
  logs/hammer_radar_forward/tiny_live*.ndjson \
  2>/dev/null || true

8. Cleanup guidance:
R302 may append logs/hammer_radar_forward/tiny_live_armed_dry_run_timer_observation_certificate.ndjson only when the explicit CLI record flag is used. Review runtime log dirt before any future commit; do not delete runtime evidence from this script.
PLAN
