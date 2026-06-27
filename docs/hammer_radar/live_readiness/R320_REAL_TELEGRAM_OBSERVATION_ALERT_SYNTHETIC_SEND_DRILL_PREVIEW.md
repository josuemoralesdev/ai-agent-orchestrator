# R320 Real Telegram Observation Alert Synthetic Send Drill Preview

R320 proves that the real Telegram alert path is ready for a future human-reviewed send gate when a synthetic actionable observation alert exists. R320 itself remains preview-only and never sends Telegram.

## What R319 Proved

R319 repaired Telegram credential readiness for the existing R318 preview. The preview can now detect credentials from the private operator env file:

```text
/home/josue/.config/hammer-radar/notifications.env
```

Readiness output reports presence and masked previews only. It must keep:

```text
telegram_config_source_kind=private_env_file
telegram_config_valid_for_future_send=true
real_send_available_for_future=true
would_send_real_telegram_now=false
real_telegram_send_called=false
real_telegram_message_sent=false
secrets_shown=false
```

## Synthetic Scenarios

- `healthy`: uses an R314-compatible healthy payload. No alert is required, and the no-heartbeat/no-actionable-alert policy blocks send-now behavior.
- `synthetic_stale_observation`: uses an R314/R317-compatible stale observation payload. R315 should produce an actionable `WARNING_PREVIEW_NO_SEND` or `CRITICAL_PREVIEW_NO_SEND` alert.
- `synthetic_final_safety_violation`: uses synthetic unsafe final-safety fields. R315 should produce `CRITICAL_PREVIEW_NO_SEND`.

All scenarios are synthetic and must report:

```text
synthetic_scenario=true
synthetic_inputs_used=true
real_runtime_mutated=false
```

## No-Real-Send Guarantee

R320 does not call Telegram, does not perform mock sends, does not mutate env/config/arming/systemd/risk contracts, and does not touch live order paths.

Required R320 send flags:

```text
telegram_send_called=false
telegram_message_sent=false
real_telegram_send_called=false
real_telegram_message_sent=false
would_send_real_telegram_now=false
real_send_preview_only=true
```

Required trading safety flags:

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
paper_live_separation_intact=true
```

## Future Exact Phrase

R320 reports the future phrase but keeps it inactive and non-executable:

```text
ENABLE REAL TELEGRAM OBSERVATION ALERT SEND
```

Expected R320 phrase fields:

```text
future_confirmation_phrase_active=false
future_confirmation_phrase_executable=false
```

## How To Run

JSON drill:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_synthetic_send_drill_preview --log-dir logs/hammer_radar_forward --json
```

Text drill:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_observation_alert_synthetic_send_drill_preview --log-dir logs/hammer_radar_forward --text
```

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward real-telegram-observation-alert-synthetic-send-drill-preview
```

Operator script:

```bash
bash scripts/hammer_print_r320_real_telegram_observation_alert_synthetic_send_drill_preview.sh
```

## Pass / Fail Meaning

Pass means:

- credentials are ready for a future send path
- healthy scenario is blocked by no-actionable-alert policy
- stale observation is actionable
- final-safety violation is critical
- future confirmation phrase is inactive and non-executable
- no Telegram send occurred
- no mutation occurred
- no secret leaked

Fail means one or more drill blockers must be repaired before any R321 apply gate is designed.

## What Not To Do

- Do not send real Telegram in R320.
- Do not add apply/send flags to the R320 script.
- Do not print tokens, full chat ids, auth headers, or `.env` values.
- Do not write env files, repo config, arming state, risk contracts, or systemd units.
- Do not start, stop, enable, disable, restart, install, or reload systemd services.
- Do not place live orders, submit payloads, call Binance order/test-order endpoints, change leverage, or change margin.
- Do not disable kill switches or mutate live flags.

## Recommended R321 Paths

If R320 is clean:

```text
R321 Human-Reviewed Real Telegram Synthetic Alert Send Apply Gate
```

This should be the first phase that prepares a real-send apply gate, still requiring exact phrase and operator action. Codex validation must still not send real Telegram.

If R320 shows blockers:

```text
R321 Real Telegram Synthetic Send Drill Preview Repair
```
