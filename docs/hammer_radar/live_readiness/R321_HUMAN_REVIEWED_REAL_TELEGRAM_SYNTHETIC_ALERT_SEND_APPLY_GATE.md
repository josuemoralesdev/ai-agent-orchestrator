# R321 Human-Reviewed Real Telegram Synthetic Alert Send Apply Gate

R321 builds the human-reviewed apply gate for a future real Telegram synthetic alert send. Codex validation remains no-real-send. The gate prepares the operator command shape, exact phrase, masked readiness checks, and safety fields without mutating live runtime state.

## What R320 Proved

R320 proved:

- real Telegram credentials can be detected through the masked readiness path
- synthetic stale-observation and final-safety scenarios are actionable
- healthy scenarios remain blocked by no-actionable-alert policy
- future real-send eligibility can be reported without sending Telegram
- confirmation remained inactive and non-executable in R320
- no Telegram send, secret leak, config mutation, arming mutation, systemd mutation, live order, submit, final command, or Binance endpoint occurred

## Exact Phrase

```text
ENABLE REAL TELEGRAM OBSERVATION ALERT SEND
```

R321 only treats this exact phrase as matched. Missing or wrong confirmation blocks apply.

## Default Preview Behavior

Default CLI behavior is preview-only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate --log-dir logs/hammer_radar_forward --json
```

Expected default fields:

```text
apply_requested=false
confirmation_phrase_matched=false
send_gate_status=REAL_TELEGRAM_SYNTHETIC_SEND_GATE_PREVIEW_READY
telegram_send_called=false
telegram_message_sent=false
real_telegram_send_called=false
real_telegram_message_sent=false
would_send_real_telegram_now=false
real_send_preview_only=true
```

## Mock Apply Behavior

Mock apply records that the gate would have sent a synthetic actionable alert through the reviewed path, but it does not call Telegram:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate \
  --log-dir logs/hammer_radar_forward \
  --apply \
  --confirmation "ENABLE REAL TELEGRAM OBSERVATION ALERT SEND" \
  --telegram-sender-mode mock \
  --json
```

For synthetic stale-observation or final-safety scenarios with credentials ready:

```text
send_gate_status=REAL_TELEGRAM_SYNTHETIC_SEND_GATE_MOCK_SENT
telegram_send_called=true
telegram_message_sent=true
real_telegram_send_called=false
real_telegram_message_sent=false
```

## Real-Disabled Behavior

`real-disabled` proves the real-send branch remains unavailable in Codex validation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate \
  --log-dir logs/hammer_radar_forward \
  --apply \
  --confirmation "ENABLE REAL TELEGRAM OBSERVATION ALERT SEND" \
  --telegram-sender-mode real-disabled \
  --json
```

Expected status:

```text
send_gate_status=REAL_TELEGRAM_SYNTHETIC_SEND_GATE_REAL_SEND_DISABLED_IN_CODEX
telegram_send_called=false
telegram_message_sent=false
real_telegram_send_called=false
real_telegram_message_sent=false
would_send_real_telegram_now=false
```

## Why Codex Cannot Send Real Telegram

R321 deliberately exposes only `mock` and `real-disabled` sender modes. There is no `real` sender mode in this phase. The module never calls `notification_watcher.send_telegram_message`; that function remains the real network boundary for later operator-reviewed work.

## Operator Preview

Use the preview-only script:

```bash
bash scripts/hammer_print_r321_real_telegram_synthetic_alert_send_apply_gate.sh
```

The script does not pass `--apply`.

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward real-telegram-synthetic-alert-send-apply-gate
```

## Later Real-Send Phase Separation

The later real-send phase must be separate from R321. It should produce a final operator-run activation packet, repeat the masked credential and safety checklist, and keep real send disabled by default until the operator decides whether to run a reviewed command.

## What Not To Do

- Do not add a real sender mode in R321.
- Do not send real Telegram during Codex validation.
- Do not print tokens, full chat ids, auth headers, or `.env` values.
- Do not write env files, repo config, arming state, risk contracts, or systemd units.
- Do not start, stop, enable, disable, restart, install, or reload systemd services.
- Do not place live orders, submit payloads, create final commands, call Binance order/test-order endpoints, change leverage, or change margin.
- Do not disable kill switches or mutate live flags.
- Do not change the first Tiny Live lane.

## Recommended R322 Paths

If R321 is clean:

```text
R322 Operator-Run Real Telegram Synthetic Alert Send Activation Packet
```

If R321 shows blockers:

```text
R322 Real Telegram Synthetic Alert Send Apply Gate Repair
```
