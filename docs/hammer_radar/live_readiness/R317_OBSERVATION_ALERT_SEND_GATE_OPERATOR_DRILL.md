# R317 Observation Alert Send Gate Operator Drill

## Why R317 Exists

R316 added a human-reviewed observation alert send gate around the R315 preview. R317 proves that gate with synthetic scenarios before any real Telegram delivery is prepared.

R317 is a mock/no-real-send drill only. It does not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate configs, mutate arming state, write env files, install or control systemd units, submit final commands, or send real Telegram.

## Scenarios

The drill runs:

- `healthy`: synthetic healthy R314 payload, R315 `alert_required=false`, R316 blocks send with `SEND_GATE_BLOCKED_NO_ALERT_REQUIRED`.
- `stale_observation`: synthetic stale tick where `last_tick_age_seconds > max_age_seconds`, R315 requires an alert, missing/wrong confirmation blocks, exact confirmation records a mock send.
- `final_safety_violation`: synthetic final safety violation with unsafe source inputs, R315 emits `CRITICAL_PREVIEW_NO_SEND`, missing/wrong confirmation blocks, exact confirmation records a mock send.

All scenarios include:

```text
synthetic_scenario=true
synthetic_inputs_used=true
real_runtime_mutated=false
```

## Mock Sender Behavior

R317 always invokes R316 with:

```text
telegram_sender_mode=mock
```

When every R316 gate passes in synthetic alert scenarios, the drill records only intended mock-send flags:

```text
telegram_send_called=true
telegram_message_sent=true
real_telegram_send_called=false
real_telegram_message_sent=false
```

Healthy state never sends.

## Exact Confirmation Phrase

The inherited R316 phrase is:

```text
SEND MULTI LANE OBSERVATION ALERTS WHEN REQUIRED
```

The drill proves missing and wrong confirmations block send attempts before the exact phrase records a mock send for actionable synthetic alerts.

## How To Run

Module:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill --log-dir logs/hammer_radar_forward --text
```

JSON:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill --log-dir logs/hammer_radar_forward --json
```

Inspect:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward observation-alert-send-gate-operator-drill
```

Operator script:

```bash
bash scripts/hammer_print_r317_observation_alert_send_gate_operator_drill.sh
```

Use `--no-write` to avoid appending the R317 drill ledger.

## Output Ledger

R317 appends drill reports to:

```text
logs/hammer_radar_forward/observation_alert_send_gate_operator_drill.ndjson
```

The drill does not write the R314, R315, or R316 ledgers while building synthetic scenario results.

## Pass And Fail Meaning

`OPERATOR_DRILL_PASSED` means:

- healthy state did not alert/send
- stale observation created an actionable synthetic alert
- final safety violation created a critical synthetic alert
- missing/wrong confirmation blocked send attempts
- exact confirmation mock-sent only when gates passed
- real Telegram flags stayed false
- live/order/config/arming/systemd mutation flags stayed locked

`OPERATOR_DRILL_FAILED` means one or more scenario proofs did not match the expected gate behavior and R318 should repair the drill or underlying gate before real delivery plumbing is prepared.

## Why No Real Telegram Yet

R317 validates gate behavior and scenario proof quality only. Real Telegram delivery is still out of scope because it needs separate operator review, delivery plumbing preview, credential hygiene, and an explicit future apply gate.

## Recommended R318 Paths

If R317 is clean:

```text
R318 Real Telegram Alert Send Gate Preview
```

R318 should prepare real Telegram delivery plumbing, still preview-only by default, and require a later explicit operator apply before real sends.

If R317 shows blockers:

```text
R318 Operator Drill Repair
```
