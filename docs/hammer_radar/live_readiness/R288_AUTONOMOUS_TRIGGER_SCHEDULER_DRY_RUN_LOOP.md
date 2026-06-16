# R288 Autonomous Trigger Scheduler Dry-Run Loop

R288 adds a scheduler-style dry-run wrapper around the R287 autonomous trigger
loop. It is visibility and audit only.

## Safety

- Live execution remains disabled.
- No order, test-order, leverage, margin, or other mutation endpoint is called.
- No executable order payload is created.
- No final live submit command is made available.
- No env file, live config, risk contract, or lane control is mutated.
- No API key, secret, signature, signed URL, or auth header is printed.
- Per-signal operator approval remains false.
- Operator role: arms/disarms lanes, tunes risk, monitors alerts/logs, and can kill the system.
- Machine role: auto-triggers later when intentionally armed and all gates are open.

## Safe One-Shot Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-once \
  --record-autonomous-trigger-scheduler \
  --operator-id local_operator \
  --reason "R288 autonomous trigger scheduler dry-run loop; no submit."
```

## Safe Bounded Loop Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-trigger-scheduler-loop \
  --max-iterations 2 \
  --sleep-seconds 0 \
  --record-autonomous-trigger-scheduler \
  --operator-id local_operator \
  --reason "R288 bounded dry-run scheduler validation; no submit."
```

`max_iterations` is capped at 20 for normal CLI use. `sleep_seconds` is bounded
and defaults to 0. R288 does not daemonize and Codex must not start a background
process for this phase.

## Optional Read-Only Binance Checks

Read-only public precision/mark-price and private account/position checks remain
explicitly gated by their existing confirmation phrases:

```bash
--load-discovered-binance-readonly-env \
--fetch-binance-readonly-precision-mark-price \
--confirm-tiny-live-binance-readonly-fetch "I CONFIRM BINANCE READONLY PRECISION MARK PRICE CHECK ONLY; NO ORDER; NO SIGNATURE; NO PRIVATE ENDPOINT." \
--fetch-binance-readonly-account-position \
--confirm-binance-readonly-account-position "I CONFIRM BINANCE READONLY ACCOUNT POSITION CHECK ONLY; NO ORDER; NO TEST ORDER; NO LEVERAGE CHANGE; NO MARGIN CHANGE."
```

## API Status

```text
GET /tiny-live/autonomous-trigger-scheduler/status
```

The endpoint returns the latest recorded scheduler packet, or an idle/not-checked
packet if none exists. It performs no private Binance fetch and sends no Telegram
message by default.

## Systemd/Timer Template

Documentation only. Do not install in this Codex phase.

`/etc/systemd/system/hammer-autonomous-trigger-scheduler.service`:

```ini
[Unit]
Description=Hammer Radar autonomous trigger scheduler dry-run tick

[Service]
Type=oneshot
WorkingDirectory=/home/josue/workspace/kernel/ai-agent-orchestrator-main
ExecStart=/home/josue/workspace/kernel/ai-agent-orchestrator-main/.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-autonomous-trigger-scheduler-once --record-autonomous-trigger-scheduler --operator-id local_operator --reason "systemd dry-run scheduler tick; no submit."
Environment=PYTHONPATH=.
```

`/etc/systemd/system/hammer-autonomous-trigger-scheduler.timer`:

```ini
[Unit]
Description=Run Hammer Radar autonomous trigger scheduler dry-run tick

[Timer]
OnCalendar=*:0/5
Persistent=false

[Install]
WantedBy=timers.target
```

Again: do not install, enable, or start these units in R288. They are templates
for later operator review.
