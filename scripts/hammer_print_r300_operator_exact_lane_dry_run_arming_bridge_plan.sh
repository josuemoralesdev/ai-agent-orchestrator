#!/usr/bin/env bash
set -euo pipefail

cat <<'R300_PLAN'
R300 PRINT ONLY - operator exact-lane dry-run arming bridge plan

This script prints commands only.
Do not run these commands from Codex when they arm or disarm dry-run state.
R300 does not arm, disarm, submit, place orders, call Binance, mutate env, or mutate live config.

1. Current R300 arming bridge API check
curl -sS 'http://127.0.0.1:8015/tiny-live/operator-exact-lane-dry-run-arming-bridge/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618' | jq .

2. Current R299 timer observation certificate check
curl -sS 'http://127.0.0.1:8015/tiny-live/real-candidate-timer-observation-certificate/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618' | jq .

3. Current R298 real-candidate bridge check
curl -sS 'http://127.0.0.1:8015/tiny-live/real-candidate-dry-run-trigger-bridge/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618' | jq .

4. Current scheduler/timer health check
curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/timer-health | jq .
curl -sS http://127.0.0.1:8015/tiny-live/autonomous-trigger-scheduler/status | jq .

5. Manual operator arm command
DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-autonomous-dry-run-arm-lane --lane-key "BTCUSDT|44m|long|ladder_close_50_618" --operator-id local_operator --reason "R300 manual operator exact-lane dry-run arm; no Codex arming; no submit; no order." --confirm-dry-run-autonomous-arming "I CONFIRM AUTONOMOUS DRY-RUN ARMING ONLY; NO REAL ORDER; NO BINANCE ORDER ENDPOINT."

6. Manual operator status command
DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-autonomous-dry-run-arming-status

7. Manual operator disarm command
DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-autonomous-dry-run-disarm-lane --lane-key "BTCUSDT|44m|long|ladder_close_50_618" --operator-id local_operator --reason "R300 manual operator exact-lane dry-run disarm; no submit; no order." --confirm-dry-run-autonomous-disarm "I CONFIRM AUTONOMOUS DRY-RUN DISARM; RETURN TO OFF."

8. Post-arm verification command
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-operator-exact-lane-dry-run-arming-bridge --lane-key "BTCUSDT|44m|long|ladder_close_50_618" --operator-id local_operator --reason "R300 post-arm verification only; no Codex arming; no submit; no order."

9. Final console check
curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '{status, operator_exact_lane_dry_run_arming_bridge_panel, real_candidate_timer_observation_certificate_panel, real_candidate_dry_run_trigger_bridge_panel, final_live_submit_command_packet, recommended_next_operator_move, safety}'

10. Safety grep
grep -R '"order_placed": true\|"binance_order_endpoint_called": true\|"binance_test_order_endpoint_called": true\|"submit_attempted": true\|"real_order_placed": true\|"final_command_available": true\|"submit_allowed": true\|"executable_payload_created": true\|"secrets_shown": true\|"live_execution_enabled": true\|"allow_live_orders": true\|"fake_candidate_used": true\|"codex_arming_performed": true\|"codex_config_mutation_performed": true' -n logs/hammer_radar_forward/tiny_live*.ndjson logs/hammer_radar_forward/*autonomous*.ndjson logs/hammer_radar_forward/*binance*.ndjson 2>/dev/null || true

11. Cleanup guidance
Review any R300 ledger rows at logs/hammer_radar_forward/tiny_live_operator_exact_lane_dry_run_arming_bridge.ndjson before deciding whether to archive them. Do not delete logs from Codex unless explicitly instructed.
R300_PLAN
