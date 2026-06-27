# R316 Human-Reviewed Observation Alert Send Gate

## Why R316 Exists

R315 built a preview-only multi-lane observation alerting layer. R316 adds a human-reviewed send gate around that preview so future operator alerts can be drilled safely before any real Telegram delivery is enabled.

Default behavior remains preview-only. R316 does not place orders, call Binance order endpoints, mutate config, mutate arming state, write env files, change systemd, disable kill switches, submit final commands, or send real Telegram during Codex validation.

## Exact Confirmation Phrase

```text
SEND MULTI LANE OBSERVATION ALERTS WHEN REQUIRED
```

The phrase must match exactly before any apply path can activate.

## Preview Behavior

Default CLI:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate --log-dir logs/hammer_radar_forward
```

Preview mode:

- builds the R315 alert preview
- reports `alert_required`
- reports the required confirmation phrase
- reports send blockers
- does not call Telegram
- does not mutate config, env, arming, systemd, risk contracts, live flags, or final command state

## Apply Behavior

Apply shape:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate \
  --log-dir logs/hammer_radar_forward \
  --apply \
  --confirmation "SEND MULTI LANE OBSERVATION ALERTS WHEN REQUIRED"
```

Apply requires:

- `--apply`
- exact confirmation phrase
- `alert_required=true`
- `alert_severity=WARNING_PREVIEW_NO_SEND` or `CRITICAL_PREVIEW_NO_SEND`
- no non-critical duplicate inside the rate-limit window
- locked safety flags

`INFO_PREVIEW_NO_SEND` never sends. Healthy state is not a heartbeat.

## No Heartbeat Spam

R316 blocks healthy no-action previews. When R315 returns `alert_required=false`, R316 reports `SEND_GATE_BLOCKED_NO_ALERT_REQUIRED` for apply attempts and keeps all Telegram send flags false.

## Mock Vs Real Sender

Default:

```text
telegram_sender_mode=mock
```

Mock mode is for tests and operator drills. When every apply gate passes, it records:

- `telegram_send_called=true`
- `telegram_message_sent=true`
- `real_telegram_send_called=false`
- `real_telegram_message_sent=false`

Real mode is reserved for a later explicitly approved operator phase. In R316 it is gated and reported as `SEND_GATE_REAL_SEND_AVAILABLE_NOT_USED_IN_CODEX`; Codex validation must not invoke a real Telegram network send.

## Output Ledger

R316 records send-gate review events in:

```text
logs/hammer_radar_forward/multi_lane_observation_alert_send_gate.ndjson
```

Use `--no-write` when a no-ledger preview is needed.

## Inspect And Script

Inspect:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward multi-lane-observation-alert-send-gate
```

Operator script:

```bash
bash scripts/hammer_print_r316_observation_alert_send_gate.sh
```

The script runs preview/default mode only. It does not pass `--apply` and does not send Telegram.

## Why Codex Validation Cannot Send

The R316 phase explicitly forbids real Telegram delivery during Codex validation. Validation may only exercise preview mode and mocked apply behavior. Real Telegram delivery needs a separate operator drill or later phase with explicit authorization.

## Safe Later Verification

A later operator drill can safely verify degraded or stale synthetic alert behavior by:

- using temporary test logs
- keeping `telegram_sender_mode=mock`
- using the exact phrase
- confirming no live flags or final commands changed
- confirming non-critical duplicate sends are rate-limited
- confirming critical repeats are visible as repeat behavior

Real Telegram should remain out of scope unless a future phase explicitly chooses it.

## Recommended R317 Paths

If R316 is clean:

```text
R317 Observation Alert Send Gate Operator Drill
```

Operator-run mock/no-send drill for degraded/stale synthetic alert only, no real Telegram yet unless explicitly chosen.

If R316 shows blockers:

```text
R317 Alert Send Gate Repair
```
