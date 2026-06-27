#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-logs/hammer_radar_forward}"
MAX_AGE_SECONDS="${MAX_AGE_SECONDS:-180}"
RATE_LIMIT_WINDOW_SECONDS="${RATE_LIMIT_WINDOW_SECONDS:-900}"

echo "R319 TELEGRAM CREDENTIAL READINESS REPAIR"
echo "log_dir: ${LOG_DIR}"
echo "mode: masked_readiness_only"
echo "credential_loader: src.app.hammer_radar.operator.notification_watcher.load_notification_config"
echo
echo "EXPECTED ENV / CONFIG NAMES"
echo "TELEGRAM_BOT_TOKEN: Telegram bot token read from process env or systemd EnvironmentFile"
echo "TELEGRAM_CHAT_ID: Telegram chat id read from process env or systemd EnvironmentFile"
echo "HAMMER_ALERT_TELEGRAM_ENABLED: optional Telegram enable flag for notification worker"
echo "systemd EnvironmentFile example: /home/josue/.config/hammer-radar/notifications.env"
echo
echo "CURRENT MASKED READINESS STATUS"
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview \
  --log-dir "${LOG_DIR}" \
  --max-age-seconds "${MAX_AGE_SECONDS}" \
  --rate-limit-window-seconds "${RATE_LIMIT_WINDOW_SECONDS}" \
  --text \
  --no-write
echo
echo "SAFE MANUAL SETUP INSTRUCTIONS"
echo "1. Edit a private operator env file outside the repo, for example /home/josue/.config/hammer-radar/notifications.env."
echo "2. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID there. Do not paste values into shell commands, terminal logs, tickets, or repo files."
echo "3. Optionally set HAMMER_ALERT_TELEGRAM_ENABLED=true only for the notification worker path that needs it."
echo "4. Re-run the validation commands below. R319 validation does not send Telegram."
echo
echo "VALIDATION COMMANDS AFTER MANUAL SETUP"
echo "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview --log-dir logs/hammer_radar_forward --json"
echo "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward real-telegram-observation-alert-send-preview --no-write"
echo "bash scripts/hammer_print_r319_telegram_credential_readiness_repair.sh"
echo
echo "SAFETY FLAGS"
echo "live_execution_enabled=false"
echo "allow_live_orders=false"
echo "global_kill_switch=true"
echo "order_placed=false"
echo "real_order_placed=false"
echo "execution_attempted=false"
echo "submit_allowed=false"
echo "final_command_available=false"
echo "real_order_forbidden=true"
echo "binance_order_endpoint_called=false"
echo "binance_test_order_endpoint_called=false"
echo "leverage_change_called=false"
echo "margin_change_called=false"
echo "secrets_shown=false"
echo "paper_live_separation_intact=true"
echo "autonomous_arming_state_changed=false"
echo "global_live_flags_changed=false"
echo "risk_contract_config_mutated=false"
echo "config_written=false"
echo "env_written=false"
echo "env_mutated=false"
echo "systemd_unit_mutated=false"
echo "scheduler_started=false"
echo "telegram_send_called=false"
echo "telegram_message_sent=false"
echo "real_telegram_send_called=false"
echo "real_telegram_message_sent=false"
echo
echo "RECOMMENDED NEXT PHASE"
echo "If credentials are still missing: R320 Operator Manual Telegram Credential Setup Checklist"
echo "If credentials are present: R320 Real Telegram Observation Alert Synthetic Send Drill Preview"
echo "If blockers remain: R320 Credential Readiness Repair Follow-up"
