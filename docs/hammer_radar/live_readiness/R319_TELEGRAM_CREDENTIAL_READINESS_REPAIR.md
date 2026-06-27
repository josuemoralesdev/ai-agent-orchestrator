# R319 Telegram Credential Readiness Repair

R319 repairs the R318 credential readiness surface only. R318 proved the real Telegram send gate preview stayed safe, but the interactive shell running readiness checks did not have real Telegram credentials available:

- `telegram_token_present=false`
- `telegram_chat_id_present=false`
- `real_send_available_for_future=false`
- blockers: `telegram_token_missing`, `telegram_chat_id_missing`

R319 does not send Telegram, write credentials, mutate env files, mutate systemd, arm live execution, submit payloads, create final commands, or call Binance endpoints.

## Expected Credential Names

The existing loader is `src.app.hammer_radar.operator.notification_watcher.load_notification_config`.

It reads:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `HAMMER_ALERT_TELEGRAM_ENABLED` for the notification worker enable flag

The active systemd services point at a private operator env file outside the repo:

```text
/home/josue/.config/hammer-radar/notifications.env
```

The readiness preview now checks credentials in this order:

1. Current process environment.
2. The private systemd `EnvironmentFile` above, only when one or both Telegram credential values are missing from the process environment.

The fallback reads only `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, never writes the file, and never prints raw values.

## Masking Policy

Readiness output reports presence and masked previews only:

- missing values print `missing`
- short values print `present_masked`
- longer values print a short prefix and suffix only
- `secrets_shown=false` must remain present

Do not paste full tokens, full chat ids, auth headers, `.env` values, or screenshots containing them into logs, issues, commits, or terminal output.

## Manual Setup

Use a private env file outside the repo. Do not put real secrets into tracked files.

Recommended location:

```text
/home/josue/.config/hammer-radar/notifications.env
```

Expected lines:

```text
TELEGRAM_BOT_TOKEN=<operator-provided-token>
TELEGRAM_CHAT_ID=<operator-provided-chat-id>
HAMMER_ALERT_TELEGRAM_ENABLED=true
```

Avoid shell history exposure by editing the file directly with a local editor rather than running `export TELEGRAM_BOT_TOKEN=...` or echoing secrets in the terminal.

## Validate Without Sending

These commands inspect readiness only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward real-telegram-observation-alert-send-preview --no-write
bash scripts/hammer_print_r319_telegram_credential_readiness_repair.sh
```

Expected JSON includes a non-null `telegram_config_readiness` object with:

- `telegram_token_present`
- `telegram_chat_id_present`
- `telegram_config_source_kind`
- `telegram_config_source_path` or `telegram_config_source_path_present`
- `telegram_token_preview`
- `telegram_chat_id_preview`
- `telegram_config_valid_for_future_send`
- `telegram_config_blockers`
- `secrets_shown=false`

On the real operator machine, when the process environment is missing credentials but `/home/josue/.config/hammer-radar/notifications.env` provides them, expected readiness is:

```text
telegram_token_present=true
telegram_chat_id_present=true
telegram_config_valid_for_future_send=true
telegram_config_source_kind=private_env_file
telegram_config_blockers=[]
real_send_available_for_future=true
real_send_blockers=[]
would_send_real_telegram_now=false
real_telegram_send_called=false
real_telegram_message_sent=false
secrets_shown=false
```

## If Credentials Are Exposed

If a token or chat id is exposed in logs, shell history, screenshots, or commits:

- rotate the Telegram bot token with BotFather
- remove or replace the exposed private env file
- clear local shell history entries that contain secrets
- review logs and commits before sharing any output
- rerun R319 readiness after rotation

## What Not To Do

- Do not send real Telegram in R319.
- Do not add send/apply flags to the R319 script.
- Do not commit real credentials or `.env` values.
- Do not write repo config with secrets.
- Do not mutate systemd units or restart services in this phase.
- Do not place live orders, submit payloads, call Binance order/test-order endpoints, change leverage, or change margin.
- Do not disable kill switches or mutate live flags.

## Recommended R320 Paths

- If credentials are still missing: `R320 Operator Manual Telegram Credential Setup Checklist`
- If credentials are present: `R320 Real Telegram Observation Alert Synthetic Send Drill Preview`
- If R319 shows blockers: `R320 Credential Readiness Repair Follow-up`

## Safety Result

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
submit_allowed=false
final_command_available=false
real_order_forbidden=true
binance_order_endpoint_called=false
binance_test_order_endpoint_called=false
leverage_change_called=false
margin_change_called=false
secrets_shown=false
paper_live_separation_intact=true
autonomous_arming_state_changed=false
global_live_flags_changed=false
risk_contract_config_mutated=false
config_written=false
env_written=false
env_mutated=false
systemd_unit_mutated=false
scheduler_started=false
telegram_send_called=false
telegram_message_sent=false
real_telegram_send_called=false
real_telegram_message_sent=false
```
