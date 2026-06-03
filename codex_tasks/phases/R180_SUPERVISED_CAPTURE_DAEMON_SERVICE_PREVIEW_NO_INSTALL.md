# R180 Supervised Capture Daemon Service Preview No Install

## Phase

R180 supervised capture daemon service preview, no install.

## Purpose

Preview a long-running supervisor service shape for the BTCUSDT 8m short capture watcher after R179 adds a paper-only supervisor command.

The preview may describe systemd and tmux service/runbook options, but must not install, enable, start, stop, restart, or mutate any service by default.

## Scope

- Reuse R179 `capture-watcher-supervisor-8m-short`.
- Preview a bounded long-running supervisor command.
- Preview service unit content or tmux command text only.
- Include operator checks for capture count, watcher heartbeat, and supervisor ledger.
- Keep the flow paper-only.

## Non-Negotiable Safety

- No config writes.
- No env writes.
- No live execution.
- No Binance calls.
- No order or test-order endpoint calls.
- No protective payloads.
- No transfers or withdrawals.
- No lane mode changes.
- Do not set the short lane `tiny_live`.
- Do not install or enable systemd services.
- Do not start, stop, or restart production services.
- Do not commit, merge, tag, or deploy.

## Expected Artifacts

- A preview-only doc under `docs/hammer_radar/live_readiness/`.
- Optional inspect command only if needed for local preview.
- Tests proving no install/start/config/live/Binance/order behavior occurs.

## Suggested Command Shape

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-watcher-supervisor-8m-short \
  --run-supervisor-loop \
  --max-supervisor-iterations 1440 \
  --sleep-seconds 60
```

Restart must remain opt-in with the R179 `--allow-paper-watcher-restart` flag and must remain paper watcher only.
