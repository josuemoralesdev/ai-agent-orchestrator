# R322 Operator-Run Real Telegram Synthetic Alert Send Activation Packet

R322 produces the final operator packet for a single real Telegram synthetic alert send review. Codex validation remains no-real-send. The packet separates safe preview commands, mock apply proof, real-disabled proof, and a manual-only real-send status.

## What R321 Proved

R321 proved:

- default preview does not send
- wrong phrase blocks apply
- exact phrase plus mock records mock send only
- exact phrase plus real-disabled blocks real send in Codex
- credentials can be detected through the masked private env readiness path
- no real Telegram send occurred
- no secret leak, env mutation, config mutation, arming mutation, systemd mutation, live order, submit, final command, or Binance endpoint occurred

## What R322 Does

R322 builds a human-readable activation packet by reusing R321 proof paths:

- safe preview
- wrong phrase block
- mock apply proof
- real-disabled proof

It writes only its own packet ledger when not run with `--no-write`:

```text
logs/hammer_radar_forward/real_telegram_synthetic_alert_activation_packet.ndjson
```

## What R322 Does Not Do

- It does not send Telegram.
- It does not add a real sender mode.
- It does not call the Telegram API.
- It does not print tokens or full chat ids.
- It does not write `.env`, config, arming state, risk contracts, or systemd units.
- It does not place orders, submit payloads, create final commands, call Binance order/test-order endpoints, change leverage, or change margin.

## Commands

Safe preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate --log-dir logs/hammer_radar_forward --json
```

Mock apply:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate --log-dir logs/hammer_radar_forward --apply --confirmation "ENABLE REAL TELEGRAM OBSERVATION ALERT SEND" --telegram-sender-mode mock --scenario synthetic_stale_observation --json
```

Real-disabled proof:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate --log-dir logs/hammer_radar_forward --apply --confirmation "ENABLE REAL TELEGRAM OBSERVATION ALERT SEND" --telegram-sender-mode real-disabled --scenario synthetic_stale_observation --json
```

Activation packet:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.real_telegram_synthetic_alert_activation_packet --log-dir logs/hammer_radar_forward --text
```

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward real-telegram-synthetic-alert-activation-packet
```

Operator script:

```bash
bash scripts/hammer_print_r322_real_telegram_synthetic_alert_activation_packet.sh
```

## Manual-Only Warning

R321 has no `real` sender mode. R322 therefore does not expose an executable real-send command. The packet marks the real-send command status as not available in current code and includes only a commented manual-only placeholder.

## Operator Abort Conditions

Abort if any of these are true:

- credentials missing
- any raw secret appears
- `real_order_forbidden=false`
- `submit_allowed=true`
- `final_command_available=true`
- config or arming diff present
- `.env` changed
- systemd service changed
- unexpected Telegram send already occurred
- alert scenario is not synthetic
- command would touch Binance or trading endpoints

## Post-R322 Recommendation

Telegram scope should stop after this packet. Recommended next phase:

```text
R323 Strategy Lab Expansion Re-entry and Candidate Surface Map
```

Return to more lanes, more entry modes, more strategy variants, more candidate surface, and Tiny Live signal readiness.
