# R208A Weekend Paper Fisherman Supervisor

R208A adds a paper-only weekend supervisor for the R198 full-spectrum harvester and the BTCUSDT 8m short paper capture watcher.

It exists because R208 showed the fisherman can go stale or exit after one capture, which can make a quiet weekend look like "no signal" when the real problem is "no watcher."

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  weekend-paper-fisherman-supervisor
```

Record after exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  weekend-paper-fisherman-supervisor \
  --record-supervisor \
  --confirm-weekend-fisherman-supervisor "I CONFIRM WEEKEND PAPER FISHERMAN SUPERVISOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation smoke:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  weekend-paper-fisherman-supervisor \
  --record-supervisor \
  --confirm-weekend-fisherman-supervisor "wrong"
```

Ledger:

```text
logs/hammer_radar_forward/weekend_paper_fisherman_supervisor.ndjson
```

## What It Checks

- R198 full-spectrum harvester heartbeat presence and freshness.
- BTCUSDT 8m short capture watcher heartbeat presence and freshness.
- Whether either watcher appears stale after 180 seconds.
- Whether R198 exited after a capture.
- Whether 8m short captures are flowing toward the 10-capture threshold.
- Whether local capture ledgers disagree or the count-sync ledger is missing.
- Whether any fresh 222m full-spectrum capture is visible.

## Weekend Policy

Acceptable:

- No fresh signal found while fisherman heartbeats are recent.

Unacceptable:

- Fisherman not running.
- Stale heartbeat.
- Harvester exited after capture without restart.

Warnings:

- Capture ledger mismatch.
- 8m short count below 10.
- Betrayal/222m context exists but is not integrated into the current matrix.

## Safe Operator Commands

The supervisor prints safe commands for:

- tmux status checks
- heartbeat tails
- 24h R198 full-spectrum harvester restart
- 24h 8m short capture watcher restart
- capture-count sync preview
- repeated R208A preview

Codex must not run these restart commands automatically in this phase.

## Betrayal / Inverse Context

R208A includes paper-only R80/R81 context:

- `222m` aggregate betrayal primary candidate from R80: original win rate `12.5%`, naive inverse `87.5%`.
- `88m` aggregate betrayal watchlist from R80: original win rate `36.67%`, naive inverse `63.33%`.
- True inverse validation remains required before any promotion.
- Betrayal is not live-ready.
- Betrayal data is not integrated into the current matrix by R208A.

## Safety State

R208A does not:

- call Binance or any network
- place orders or create order payloads
- call order, test-order, transfer, or withdraw endpoints
- write env/config/lane/risk/registry/scoring/matrix config
- change lane mode or set any lane `tiny_live`
- promote signal origins or lanes
- disable the kill switch
- authorize live execution

Capture/fishing status is operator visibility only. It must not be interpreted as live readiness.
