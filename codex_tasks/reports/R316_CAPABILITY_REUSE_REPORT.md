# R316 Capability Reuse Report

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification: DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM
- Reason: R316 adds a send gate around the existing R315 preview alert decision. It is intentionally close to existing notification and Telegram code, so the implementation must reuse the preview decision and avoid creating a second alert rule engine.

## Capability Scan

### Reusable Preview Alert Decision Source

`src/app/hammer_radar/operator/multi_lane_observation_alerting_preview.py` already provides the correct decision source for R316:

- `build_multi_lane_observation_alerting_preview`
- `alert_required`
- `alert_severity`
- `alert_reasons`
- `telegram_preview_message`
- `operator_console_preview_message`
- `dedup_key`
- `would_suppress_duplicate`
- `would_repeat_critical`
- locked safety fields

R316 reuses that function instead of re-implementing health/timer/lane/paper/final-live checks.

### R314 Health Source

`src/app/hammer_radar/operator/multi_lane_observation_health_panel.py` remains the underlying health input. It reads observation, timer, paper refresh, and final live safety state, while preserving:

- no order placement
- no submit
- no final command
- no config/env/systemd mutation
- local safety fields

### R315 Operator Surfaces

`scripts/hammer_print_r315_multi_lane_observation_alerting_preview.sh` and `docs/hammer_radar/live_readiness/R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW.md` establish the preview-only operator pattern. R316 follows the same CLI and text-output style, but adds confirmation and send-gate status fields.

The existing ledger `logs/hammer_radar_forward/multi_lane_observation_alerting_preview.ndjson` shows healthy-state records with:

- `alert_required=false`
- `alert_severity=INFO_PREVIEW_NO_SEND`
- `telegram_send_called=false`
- `telegram_message_sent=false`
- final live safety locked

### Reusable Telegram Send Function

`src/app/hammer_radar/operator/notification_watcher.py` has `send_telegram_message(token, chat_id, message)`, plus config loading and existing notification dedupe helpers.

R316 does not call this function during Codex validation. The phase introduces a human-reviewed gate around the R315 alert decision and defaults to `telegram_sender_mode=mock`. Real Telegram delivery remains a future operator action because this phase explicitly forbids real Telegram send in validation.

### Telegram Mocking And Transport Boundaries

Existing Telegram test patterns use injectable transport or sender functions:

- `notification_watcher.check_notifications(..., telegram_sender=...)`
- `telegram_polling_worker.poll_telegram_once(..., transport=...)`

R316 follows that approach at the behavioral level: mock mode records intended send fields in the R316 output and ledger without network use. The mock apply path is only active when all gates pass:

- `--apply`
- exact confirmation phrase
- `alert_required=true`
- `alert_severity` is `WARNING_PREVIEW_NO_SEND` or `CRITICAL_PREVIEW_NO_SEND`
- duplicate/rate-limit policy permits the send

### Inspect Route

`src/app/hammer_radar/operator/inspect.py` already exposes R314 and R315 inspect commands. R316 adds:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward multi-lane-observation-alert-send-gate
```

This route runs preview/default mode only.

### Duplicate Risks

Similar existing modules:

- `multi_lane_observation_alerting_preview.py`: alert decision and preview message source
- `notification_watcher.py`: Telegram alert send and dedupe for readiness notifications
- `telegram_polling_worker.py`: Telegram polling/send transport boundary
- `telegram_operator_bridge.py`: inbound operator command safety
- `telegram_approval_challenge.py`: exact human confirmation pattern

Risk:

- duplicating alert rules from R315
- accidentally treating healthy INFO preview as a sendable heartbeat
- accidentally calling real Telegram
- confusing alert visibility with live/trade authorization

Mitigation:

- R316 imports and reuses R315 preview output
- INFO previews always block apply
- default sender mode is mock
- real-mode output is explicitly `SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX`
- no real Telegram function is called in R316 tests or validation
- all required no-live and no-mutation flags remain in every output

## No-Heartbeat Policy

Healthy observation state is not actionable. When R315 reports:

- `alert_required=false`
- `alert_severity=INFO_PREVIEW_NO_SEND`

R316 blocks apply with `SEND_GATE_BLOCKED_NO_ALERT_REQUIRED`. This prevents heartbeat spam and prevents "everything is fine" Telegram messages.

## Exact Send-Gate Requirements

The exact confirmation phrase is:

```text
SEND MULTI LANE OBSERVATION ALERTS WHEN REQUIRED
```

Real or mock send paths require:

- `alert_required=true`
- exact confirmation phrase matched
- `--apply`
- severity `WARNING_PREVIEW_NO_SEND` or `CRITICAL_PREVIEW_NO_SEND`
- no non-critical duplicate inside the rate-limit window
- safety flags locked
- no live/trade implication

## Why Real Telegram Is Not Called In R316 Validation

R316 validation is forbidden from sending real Telegram. Therefore:

- default mode is preview only
- default sender mode is mock
- tests use mock apply only
- `real_telegram_send_called=false`
- `real_telegram_message_sent=false`
- no Telegram token or chat id is read or printed
- no network sender is invoked by R316 validation
