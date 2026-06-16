#!/usr/bin/env bash
set -euo pipefail

cat <<'PLAN'
R298 PRINT ONLY - real-candidate dry-run trigger bridge plan

This script prints commands only. It does not run sudo, systemctl, curl, order
commands, install, cp, mv, rm, or cleanup commands.

=== Fresh trigger watch check ===
curl -sS http://127.0.0.1:8015/tiny-live/fresh-trigger-watch | jq '{
  event_type,
  status,
  current_fresh_candidate_exists,
  current_candidate_lane_key,
  qualified_fresh_candidate_exists,
  qualified_fresh_candidate_lane_keys,
  live_qualified_lanes,
  safety
}'

=== R298 CLI bridge check ===
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-real-candidate-dry-run-trigger-bridge \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R298 real-candidate dry-run trigger bridge; no fake candidate; no submit; no order." \
  --record-real-candidate-dry-run-trigger-bridge \
  | tee /tmp/r298_real_candidate_dry_run_trigger_bridge.json \
  | jq '{
    event_type,
    status,
    requested_lane_key,
    current_real_candidate_exists,
    current_real_candidate_lane_key,
    current_real_candidate_signal_id,
    current_real_candidate_freshness_status,
    current_real_candidate_live_qualification_class,
    candidate_matches_requested_lane,
    lane_is_live_qualified,
    exact_lane_only,
    no_cross_lane_borrowing,
    real_candidate_source,
    test_only,
    fake_candidate_used,
    dry_run_only,
    live_execution_enabled,
    allow_live_orders,
    global_kill_switch,
    timer_health_status,
    timer_active,
    recent_tick_seen,
    r297_test_only_path_certified_seen,
    real_candidate_bridge_supported,
    simulated_dry_run_trigger_recorded,
    simulated_lifecycle_status,
    simulated_open_record,
    simulated_protective_orders,
    simulated_close_plan,
    no_matching_candidate_action,
    final_command_available,
    submit_allowed,
    real_order_forbidden,
    executable_payload_created,
    order_payload_created,
    order_placed,
    binance_order_endpoint_called,
    binance_test_order_endpoint_called,
    per_signal_operator_approval_required,
    blockers,
    safety
  }'

=== R298 API status check ===
curl -sS http://127.0.0.1:8015/tiny-live/real-candidate-dry-run-trigger-bridge/status | jq '{
  event_type,
  status,
  real_candidate_dry_run_trigger_bridge_panel,
  final_command_available,
  submit_allowed,
  real_order_forbidden,
  safety
}'

=== Final console check ===
curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '{
  status,
  real_candidate_dry_run_trigger_bridge_panel,
  timer_integrated_test_only_matching_trigger_rehearsal_panel,
  test_only_matching_candidate_trigger_certificate_panel,
  timer_observed_armed_lane_wait_certificate_panel,
  dry_run_lane_arming_rehearsal_panel,
  final_live_submit_command_packet,
  recommended_next_operator_move,
  safety
}'

=== Safety grep ===
grep -R "\"order_placed\": true\|\"binance_order_endpoint_called\": true\|\"binance_test_order_endpoint_called\": true\|\"submit_attempted\": true\|\"real_order_placed\": true\|\"final_command_available\": true\|\"submit_allowed\": true\|\"executable_payload_created\": true\|\"secrets_shown\": true\|\"live_execution_enabled\": true\|\"allow_live_orders\": true" -n \
  logs/hammer_radar_forward/tiny_live*.ndjson \
  logs/hammer_radar_forward/*autonomous*.ndjson \
  logs/hammer_radar_forward/*binance*.ndjson \
  2>/dev/null || true

=== Cleanup guidance ===
# Review generated local runtime evidence:
#   logs/hammer_radar_forward/tiny_live_real_candidate_dry_run_trigger_bridge.ndjson
#   /tmp/r298_real_candidate_dry_run_trigger_bridge.json
# Remove only after operator review if you intentionally want to clear local R298 evidence.
PLAN
