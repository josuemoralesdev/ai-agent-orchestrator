#!/usr/bin/env bash
set -euo pipefail

cat <<'PLAN'
R303 PRINT ONLY - final tiny-live authorization gate plan

This script prints commands only. It does not execute curl, order submit, sudo,
systemctl, install, cp, mv, rm, or Binance calls.

=== R302 check ===
curl -sS 'http://127.0.0.1:8015/tiny-live/armed-dry-run-timer-observation-certificate/status?lane_key=BTCUSDT%7C44m%7Clong%7Cladder_close_50_618' | jq '{status, requested_lane_key, exact_lane_auto_armed, armed_lane_key, current_real_candidate_exists, final_command_available, submit_allowed, real_order_forbidden, blockers}'

=== R303 API check ===
curl -sS 'http://127.0.0.1:8015/tiny-live/final-authorization-gate/status?lane_key=BTCUSDT%7C44m%7Clong%7Cladder_close_50_618' | jq '{event_type, status, requested_lane_key, exact_lane_auto_armed, armed_lane_key, current_real_candidate_exists, current_real_candidate_lane_key, current_real_candidate_signal_id, candidate_matches_requested_lane, exact_lane_risk_contract_found, exact_lane_risk_contract_valid, protective_triplet_preview_available, protective_triplet_preview_valid, binance_readiness_ready, leverage_margin_ready, wallet_ready, no_conflicting_position, idempotency_clean, prior_live_submit_found, final_command_available, submit_allowed, real_order_forbidden, executable_payload_created, order_payload_created, order_placed, binance_order_endpoint_called, binance_test_order_endpoint_called, blockers}'

=== R303 CLI review command ===
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-authorization-gate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R303 final tiny-live authorization gate review; no submit; no order." \
  --record-final-authorization-gate \
  | tee /tmp/r303_final_authorization_gate.json \
  | jq '{event_type, status, requested_lane_key, exact_lane_auto_armed, armed_lane_key, current_real_candidate_exists, current_real_candidate_lane_key, current_real_candidate_signal_id, candidate_matches_requested_lane, exact_lane_risk_contract_found, exact_lane_risk_contract_valid, protective_triplet_preview_available, protective_triplet_preview_valid, binance_readiness_ready, leverage_margin_ready, wallet_ready, no_conflicting_position, idempotency_clean, prior_live_submit_found, final_command_available, submit_allowed, real_order_forbidden, executable_payload_created, order_payload_created, order_placed, binance_order_endpoint_called, binance_test_order_endpoint_called, blockers}'

=== Final console panel check ===
curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '.final_tiny_live_authorization_gate_panel'

=== Manual disarm command ===
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-dry-run-disarm-lane \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R303 manual operator rollback/disarm dry-run arming; no submit; no order." \
  --confirm-dry-run-autonomous-disarm "I CONFIRM DISARM AUTONOMOUS DRY RUN TINY LIVE LANE; NO LIVE ORDER; NO CONFIG MUTATION OUTSIDE AUTONOMOUS ARMING STATE."

=== Safety grep ===
grep -R "\"order_placed\": true\|\"binance_order_endpoint_called\": true\|\"binance_test_order_endpoint_called\": true\|\"secrets_shown\": true\|\"fake_candidate_used\": true" -n \
  logs/hammer_radar_forward/tiny_live_final_authorization_gate.ndjson \
  logs/hammer_radar_forward/tiny_live*.ndjson \
  2>/dev/null || true

=== If READY ===
If R303 status is FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT,
review .final_manual_submit_packet and .final_manual_submit_command. The packet
must say MANUAL_OPERATOR_ONLY, ONE_SHOT_TINY_LIVE, EXACT_LANE_ONLY,
NO_CROSS_LANE_BORROWING, reduce-only protective orders required, and must not
contain secrets, signatures, or signed URLs.

=== Cleanup guidance ===
R303 CLI review with --record-final-authorization-gate appends only:
logs/hammer_radar_forward/tiny_live_final_authorization_gate.ndjson
Keep runtime logs for audit unless the operator explicitly requests cleanup.
PLAN
