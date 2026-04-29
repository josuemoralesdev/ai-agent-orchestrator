# Hammer Paper Refresh Service

`hammer-paper-refresh.service` runs the Hammer Radar paper refresh scheduler as a supervised systemd service.

The service executes:

```bash
/home/josue/workspace/kernel/ai-agent-orchestrator-main/.venv/bin/python -m src.app.hammer_radar.operator.paper_refresh_scheduler --watch
```

## Safety Guarantees

- Paper/watch refresh only.
- No live orders.
- No ETH/alt live tickets.
- BTCUSDT remains the only live-readiness symbol.
- ETHUSDT remains paper-only.
- ETHBTC remains rotation context only.
- Secrets are loaded only from optional environment files and are never written into the unit.

Reminder: No live orders. No ETH/alt live tickets. BTCUSDT remains the only live-readiness symbol.

## Install

Review the unit first:

```bash
sed -n '1,220p' ops/systemd/hammer-paper-refresh.service
```

Install and enable without starting:

```bash
bash ops/systemd/install_hammer_paper_refresh_service.sh
```

Install, enable, and start:

```bash
bash ops/systemd/install_hammer_paper_refresh_service.sh --start
```

Manual install equivalent:

```bash
sudo install -m 0644 ops/systemd/hammer-paper-refresh.service /etc/systemd/system/hammer-paper-refresh.service
sudo systemctl daemon-reload
sudo systemctl enable hammer-paper-refresh.service
```

Start or stop manually:

```bash
sudo systemctl start hammer-paper-refresh.service
sudo systemctl stop hammer-paper-refresh.service
```

## Status And Logs

```bash
systemctl status hammer-paper-refresh.service --no-pager
journalctl -u hammer-paper-refresh.service -n 80 --no-pager
curl -s http://127.0.0.1:8015/paper-refresh/status
curl -s http://127.0.0.1:8015/paper-refresh/runs
```

## Rollback

```bash
sudo systemctl disable --now hammer-paper-refresh.service
sudo rm /etc/systemd/system/hammer-paper-refresh.service
sudo systemctl daemon-reload
```

## Environment

The unit uses:

```text
HAMMER_RADAR_LOG_DIR=/home/josue/workspace/kernel/ai-agent-orchestrator-main/logs/hammer_radar_forward
HAMMER_REFRESH_USE_NETWORK=false
HAMMER_REFRESH_WRITE_OUTPUTS=true
HAMMER_REFRESH_SEND_NOTIFICATIONS=true
HAMMER_REFRESH_POLL_SECONDS=300
```

Optional environment files are loaded if present:

```text
/home/josue/.config/hammer-radar/binance-readonly.env
/home/josue/.config/hammer-radar/notifications.env
```

No tokens, API keys, or secrets belong in this repository.
