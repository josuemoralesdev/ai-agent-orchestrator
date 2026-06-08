# R235 Lightweight Tiny-Live Wait Status

## Purpose

Create a lightweight status-only phase that checks whether the official protected tiny-live path has reached 10/10 while keeping near-threshold and betrayal gate-prepared context visible.

## Required Scope

- Check official `BTCUSDT|8m|short|ladder_close_50_618` fresh capture threshold.
- Check 8m long near-threshold status.
- Check fisherman/watcher alive and stale status.
- Check latest R234 betrayal gate-ready packet status.
- Recommend R228 only when the official 8m short threshold is 10/10.
- Otherwise recommend waiting / keeping fisherman running.

## Safety

- No config writes.
- No env writes.
- No lane mode changes.
- No risk contract writes.
- No Binance/network calls.
- No order payloads.
- No live execution.
- No transfers or withdrawals.
- No kill switch disable.
- No signal origin, lane, alternate, or betrayal promotion.

## Expected Command Shape

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lightweight-tiny-live-wait-status
```

## Expected Inputs

- `logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson`
- `logs/hammer_radar_forward/capture_priority_rebalance.ndjson`
- `logs/hammer_radar_forward/lane_outcome_enrichment.ndjson`
- `logs/hammer_radar_forward/weekend_paper_fisherman_supervisor.ndjson`
- `logs/hammer_radar_forward/fisherman_watchdog_ledger_reconciliation.ndjson`
- `logs/hammer_radar_forward/betrayal_gate_ready_lane_packet.ndjson`

## Expected Output

- Official tiny-live threshold state.
- 8m long alternate watch state.
- Fisherman/watcher health.
- Betrayal gate-ready packet status.
- Recommended next operator move.
- Safety object proving no live/order/config/network action.
