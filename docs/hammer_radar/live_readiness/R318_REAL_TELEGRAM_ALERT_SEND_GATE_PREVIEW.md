# R318 Real Telegram Alert Send Gate Preview

R318 prepares real Telegram delivery plumbing for future observation alerts while staying preview-only. It follows R317, which proved the R316 alert send gate with synthetic mock/no-real-send scenarios and kept real Telegram, config, arming, systemd, live order, submit, and final-command flags false.

## Behavior

- Checks Telegram credential presence through the existing notification config loader.
- Masks token and chat id previews; full credential values are never printed.
- Reuses the R315 alert preview and R316 send-gate preview.
- Does not pass any apply/send flag.
- Does not call the Telegram send endpoint.
- Does not send heartbeat/no-alert messages when `alert_required=false`.
- Preserves dedup/rate-limit preview fields for future compatibility.

## Future Confirmation Phrase

The exact future phrase is:

```text
ENABLE REAL TELEGRAM OBSERVATION ALERT SEND
```

In R318 it is inactive and non-executable:

```text
future_confirmation_phrase_active=false
future_confirmation_phrase_executable=false
would_send_real_telegram_now=false
```

## Credential Hygiene

R318 outputs only:

- `telegram_token_present`
- `telegram_chat_id_present`
- `telegram_config_source_kind`
- `telegram_token_preview`
- `telegram_chat_id_preview`
- `telegram_config_valid_for_future_send`
- `telegram_config_blockers`
- `secrets_shown=false`

Masked previews use short boundary characters only, or `present_masked` for short values.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward real-telegram-observation-alert-send-preview
bash scripts/hammer_print_r318_real_telegram_observation_alert_send_preview.sh
```

## What Not To Do

- Do not send real Telegram in R318.
- Do not add apply/send flags to the R318 script.
- Do not print tokens, chat ids, `.env` values, or auth headers.
- Do not mutate config, env, arming state, risk contracts, live flags, or systemd units.
- Do not place orders, submit payloads, call Binance order endpoints, or create final commands.

## Recommended R319 Paths

- If R318 is clean and credentials are present: `R319 Real Telegram Observation Alert Synthetic Send Drill Preview`.
- If credentials are missing: `R319 Telegram Credential Readiness Repair`.
- If R318 shows blockers: `R319 Real Telegram Preview Repair`.
