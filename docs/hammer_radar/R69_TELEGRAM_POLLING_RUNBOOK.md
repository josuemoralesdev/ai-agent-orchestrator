# R69 Telegram Polling Runbook

Purpose: run the Hammer Radar Telegram inbound operator loop continuously so chat commands are processed without manually calling `/telegram/polling/once`.

Safety guarantees:
- Polling routes text through the same `/telegram/operator-command` handler.
- It does not place orders, fund accounts, edit env files, or call Binance live order endpoints.
- Raw `YES` remains rejected and `trade now live` remains blocked.
- `LIVE APPROVE <signal_id>` remains exact-signal only and still depends on strict first-live freshness.
- Telegram token and chat id are not printed in status or event records.

Manual one-shot test:

```bash
curl --max-time 20 -s -X POST http://127.0.0.1:8015/telegram/polling/once \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":false}' | jq .
```

Manual foreground watch test:

```bash
cd /home/josue/workspace/kernel/ai-agent-orchestrator-main
.venv/bin/python -m src.app.hammer_radar.operator.telegram_polling_worker --watch
```

Status checks:

```bash
curl --max-time 10 -s http://127.0.0.1:8015/telegram/polling/status | jq .
curl --max-time 10 -s http://127.0.0.1:8015/telegram/polling/state | jq .
```

Manual systemd install:

```bash
sudo cp deploy/systemd/hammer-telegram-polling.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hammer-telegram-polling.service
systemctl status hammer-telegram-polling.service --no-pager
journalctl -u hammer-telegram-polling.service -f
```

Rollback:

```bash
sudo systemctl disable --now hammer-telegram-polling.service
sudo rm /etc/systemd/system/hammer-telegram-polling.service
sudo systemctl daemon-reload
```

Expected behavior:
- `FIRST LIVE NEXT` replies quickly.
- `FIRST LIVE CHAIN` replies quickly.
- `LIVE APPROVE <signal_id>` is accepted only for the current strict-fresh first-live signal.
- No order is placed, no real order is placed, and secrets remain hidden.
