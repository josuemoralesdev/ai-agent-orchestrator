#!/usr/bin/env bash
set -euo pipefail

cat <<'R301_PLAN'
R301 PRINT ONLY - manual operator dry-run arming post-arm certificate plan

This script prints commands only.
Do not run arming or disarming commands from Codex.
R301 does not arm, disarm, submit, place orders, call Binance, mutate env, mutate live config, or mutate autonomous arming config.

1. Current R300 bridge API check
curl -sS 'http://127.0.0.1:8015/tiny-live/operator-exact-lane-dry-run-arming-bridge/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618' | jq .

2. Current R301 post-arm certificate API check
curl -sS 'http://127.0.0.1:8015/tiny-live/manual-operator-dry-run-arming-post-arm-certificate/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618' | jq .

3. Manual operator arm command
DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-autonomous-dry-run-arm-lane --lane-key "BTCUSDT|44m|long|ladder_close_50_618" --operator-id local_operator --reason "R301 manual operator exact-lane dry-run arm outside Codex; no submit; no order." --confirm-dry-run-autonomous-arming "I CONFIRM AUTONOMOUS DRY-RUN ARMING ONLY; NO REAL ORDER; NO BINANCE ORDER ENDPOINT."

4. Manual post-arm verification command
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-manual-operator-dry-run-arming-post-arm-certificate --lane-key "BTCUSDT|44m|long|ladder_close_50_618" --operator-id local_operator --reason "R301 post-arm verification only; no Codex arming; no submit; no order." --record-manual-operator-dry-run-arming-post-arm-certificate

5. Manual disarm rollback command
DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER:
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-autonomous-dry-run-disarm-lane --lane-key "BTCUSDT|44m|long|ladder_close_50_618" --operator-id local_operator --reason "R301 manual rollback/disarm exact-lane dry-run arming; no submit; no order." --confirm-dry-run-autonomous-disarm "I CONFIRM AUTONOMOUS DRY-RUN DISARM; RETURN TO OFF."

6. Final console panel check
curl -sS http://127.0.0.1:8015/tiny-live/final-console | jq '.manual_operator_dry_run_arming_post_arm_certificate_panel'

7. Safety grep
grep -R '"order_placed": true\|"binance_order_endpoint_called": true\|"binance_test_order_endpoint_called": true\|"submit_allowed": true\|"final_command_available": true\|"executable_payload_created": true\|"codex_arming_performed": true\|"codex_config_mutation_performed": true\|"live_execution_enabled": true\|"allow_live_orders": true' -n logs/hammer_radar_forward/tiny_live_manual_operator_dry_run_arming_post_arm_certificate.ndjson logs/hammer_radar_forward/tiny_live*.ndjson 2>/dev/null || true

8. Cleanup guidance
Review any R301 ledger rows at logs/hammer_radar_forward/tiny_live_manual_operator_dry_run_arming_post_arm_certificate.ndjson before deciding whether to archive them. Do not delete logs from Codex unless explicitly instructed.
R301_PLAN
