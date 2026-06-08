# R208B Fisherman Watchdog Ledger Reconciliation

R208B adds a paper-only reconciliation surface for the BTCUSDT 8m short fisherman/watchdog count path.

It exists because R208A can correctly detect a missing `capture_count_sync_8m_short.ndjson` ledger, but the operator needs a clean way to preview and, after explicit confirmation, append a reconciled count record from local paper ledgers only.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fisherman-watchdog-ledger-reconciliation
```

Record after exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fisherman-watchdog-ledger-reconciliation \
  --record-reconciliation \
  --confirm-fisherman-watchdog-ledger-reconciliation "I CONFIRM FISHERMAN WATCHDOG LEDGER RECONCILIATION ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation smoke:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fisherman-watchdog-ledger-reconciliation \
  --record-reconciliation \
  --confirm-fisherman-watchdog-ledger-reconciliation "wrong"
```

Ledgers:

```text
logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson
logs/hammer_radar_forward/fisherman_watchdog_ledger_reconciliation.ndjson
```

## What It Checks

- BTCUSDT 8m short capture watcher heartbeat presence and freshness.
- R198 full-spectrum harvester heartbeat presence and freshness.
- Short paper capture records.
- Full-spectrum harvest captures for the primary 8m short lane only.
- Existing capture-count sync records when present.
- Missing `capture_count_sync_8m_short.ndjson`.
- Whether a reconciled capture count can be rebuilt from local paper-only evidence.

## Count Rules

- Counts unique `captured_signal_id` / local signal ids only.
- Counts only the primary `BTCUSDT|8m|short|ladder_close_50_618` lane or compatible `BTCUSDT|8m|short|timestamp` signal ids.
- Does not count duplicate signal ids.
- Does not count non-8m-short lanes.
- Does not mark threshold met unless unique local captures are at least `10`.

## Recording Rules

Preview mode writes nothing.

Record mode appends exactly one rebuilt count-sync record and one R208B audit record only when the exact confirmation phrase is supplied. It does not rewrite existing ledger lines.

Rejected confirmation writes nothing.

## Safety State

R208B does not:

- call Binance or any network
- place orders or create order payloads
- call order, test-order, transfer, or withdraw endpoints
- write env/config/lane/risk/registry/scoring/matrix config
- change lane mode or set any lane `tiny_live`
- promote signal origins or lanes
- disable the kill switch
- authorize live execution
- infer funding readiness
- infer live readiness

The output is operator truth for paper ledger reconciliation only. Even at `10/10`, R228 or later must remain checklist-only unless a future phase explicitly authorizes otherwise.
