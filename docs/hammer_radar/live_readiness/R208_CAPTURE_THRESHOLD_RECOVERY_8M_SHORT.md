# R208 Capture Threshold Recovery 8m Short

R208 reconciles local paper-capture visibility for the primary lane:

```text
BTCUSDT|8m|short|ladder_close_50_618
```

It reads R198 full-spectrum harvester heartbeats and capture records, R157/R176 short paper capture ledgers, and the R176 capture-count sync ledger. It reports whether the 8m short count is still below 10, has reached 10, is stale, or is blocked by a ledger mismatch.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-threshold-recovery-8m-short
```

Record after exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  capture-threshold-recovery-8m-short \
  --record-recovery \
  --confirm-capture-threshold-recovery "I CONFIRM CAPTURE THRESHOLD RECOVERY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/capture_threshold_recovery_8m_short.ndjson
```

R208 is diagnostic/audit only. It does not run tmux or `ps` itself; it emits safe operator commands for tmux status, heartbeat tailing, R198 harvester restart, and R176 count recheck.

Safety state:

- no Binance/network calls
- no env/config/lane/risk-contract writes
- no order, test-order, transfer, withdraw, signed request, or executable payload
- no live flag arming
- no kill-switch disable
- no lane or signal-origin promotion
- no tiny-live authorization

Capture recovery can improve visibility, but it cannot create live readiness. Funding, risk contract, lane mode, approval, live flags, kill switch, and final review remain separate blockers.
