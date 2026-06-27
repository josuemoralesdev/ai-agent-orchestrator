# R318 Capability Reuse Report

## Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification: DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM
- Reason: R318 resembles existing notification and R315/R316 alert-preview surfaces, so it reuses them and adds only a preview packet for future real Telegram readiness.

## Capability Scan Summary

- `multi_lane_observation_alert_send_gate.py`: R316 already gates alert sends, defaults to preview/mock, supports rate-limit/dedup checks, and never calls real Telegram during validation.
- `observation_alert_send_gate_operator_drill.py`: R317 already proves healthy no-send, stale mock-send, final safety mock-send, exact confirmation, no real Telegram, and no mutation.
- `multi_lane_observation_alerting_preview.py`: R315 already builds alert_required, severity, reasons, Telegram/operator messages, dedup keys, and rate-limit preview.
- `multi_lane_observation_health_panel.py`: R314 provides the health and safety source fields used by R315.
- `notification_watcher.py`: Provides reusable `load_notification_config`, credential presence booleans, safe status patterns, `send_telegram_message`, and dedupe concepts.
- `telegram_operator_bridge.py`: Existing Telegram command surface is record-only and reinforces exact operator command discipline.
- `telegram_polling_worker.py`: Existing real Telegram transport exists for polling responses but is not used by R318 because R318 must not send.
- `telegram_approval_challenge.py`: Existing challenge flow masks sensitive approval codes and keeps approval separate from execution.
- `configs` and env loading: Telegram credentials are loaded from env by `load_notification_config`; R318 does not read `.env` files directly and does not write config.
- R316/R317 scripts: Existing scripts print preview/drill output without real send flags.
- R317 ledger: Confirms prior drill outputs passed and real Telegram send flags remained false.
- Existing tests: R315/R316/R317 tests already cover preview, mock send, no real send, no mutation, inspect routes, and scripts.
- Existing inspect commands: R314-R317 commands are wired in `inspect.py`; R318 extends that same pattern.

## Reuse / Extend / Create Decision

- Existing capability reused: R315 alert preview, R316 send gate preview, R314 safety fields, notification config loader.
- Existing capability extended: `inspect.py` gains a new R318 command.
- New capability created: `real_telegram_observation_alert_send_preview.py`.
- Why new code was necessary: R318 needs a distinct output contract for masked credential readiness and future real-send capability without altering R316 mock/apply behavior.
- Why this is not duplicating prior work: R318 does not reimplement alert scoring, send gate status, or Telegram config loading; it composes existing modules and adds only preview-only readiness metadata.

## Credential Hygiene Policy

- Never print token, chat id, `.env`, auth headers, or full credential values.
- Output only presence booleans and masked previews.
- Always set `secrets_shown=false`.
- Treat chat id as sensitive enough to mask.

## Real Sender Preview Strategy

- Confirm `send_telegram_message` is importable/callable.
- Confirm token/chat id presence through existing env-backed config loading.
- Set `real_send_available_for_future=true` only when credentials and sender are present.
- Keep `would_send_real_telegram_now=false`.
- Keep `telegram_send_called=false`, `telegram_message_sent=false`, `real_telegram_send_called=false`, and `real_telegram_message_sent=false`.

## Future Confirmation Phrase

```text
ENABLE REAL TELEGRAM OBSERVATION ALERT SEND
```

R318 exposes the phrase as required for future work but marks it inactive and non-executable.

## Why R318 Does Not Send

R318 is a readiness preview. It validates plumbing and output hygiene only. It does not pass an apply flag, does not call a Telegram transport, and does not create a runnable real-send path.

## No-Heartbeat Policy

When `alert_required=false`, R318 sets `healthy_state_send_blocked=true` and recommends `continue_observation_no_send`. Healthy state must not produce heartbeat spam.

## Duplicate Risks

- Similar existing modules: R315 alerting preview, R316 send gate, notification watcher.
- Similar existing endpoints/commands: R314-R317 inspect routes and scripts.
- Risk: A second send path could bypass R316 confirmation or notification dedupe.
- Mitigation: R318 calls R316 in preview mode only, does not send, and exposes inactive/non-executable future confirmation fields.

## Recommended Future Apply Drill

If credentials are present and R318 remains clean, R319 should be a synthetic send drill preview that still performs no real send by default and tests the exact phrase against a synthetic stale alert. If credentials are missing, R319 should repair documentation/readiness only.
