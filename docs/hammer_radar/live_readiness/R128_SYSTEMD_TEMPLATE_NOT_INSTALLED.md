# R128 Systemd Template Not Installed

Status: NOT INSTALLED

This file is documentation only.

Do not copy blindly.

No real orders.

R128 does not install, enable, start, stop, or restart any systemd service or timer.

## Review-Only Service Template

```ini
[Unit]
Description=Hammer Radar R128 Lane Autonomy Scheduler Preview
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/josue/workspace/kernel/ai-agent-orchestrator-main
Environment=PYTHONPATH=.
ExecStart=/home/josue/workspace/kernel/ai-agent-orchestrator-main/.venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward lane-autonomy-scheduler
```

## Review-Only Timer Template

```ini
[Unit]
Description=Hammer Radar R128 Lane Autonomy Scheduler Preview Timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=false

[Install]
WantedBy=timers.target
```

## Safety Notes

- NOT INSTALLED.
- NOT ENABLED.
- DO NOT COPY BLINDLY.
- NO REAL ORDERS.
- Preview mode writes no scheduler ticks and no decisions.
- Confirmed recording still writes only local append-only audit records.
- This template must be reviewed in a future operations phase before any install command is considered.
