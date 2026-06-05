# R196 Full-Spectrum Paper Coverage Audit

R196 adds an audit-only operator surface that checks whether Hammer Radar is watching the full paper universe before more tiny-live readiness work.

Command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  full-spectrum-paper-coverage-audit
```

Optional append-only recording requires the exact phrase:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  full-spectrum-paper-coverage-audit \
  --record-audit \
  --confirm-full-spectrum-paper-audit "I CONFIRM FULL SPECTRUM PAPER COVERAGE AUDIT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/full_spectrum_paper_coverage_audit.ndjson
```

The audit reads:

- `configs/hammer_radar/lane_controls.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- paper signals, scans, executions, outcomes, harvester, ranking, watcher, registry, scoring, detector, and matrix ledgers under `logs/hammer_radar_forward/`

It reports:

- configured lanes, paper lanes, and tiny-live lanes as reference-only
- symbols and timeframes discovered from configs/logs
- lane, timeframe, symbol, and signal-origin coverage matrices
- blind spots such as configured-not-harvested, signals-present-not-configured, outcomes-without-watcher, and registered-origins-without-detectors
- next action plan for R197 detector family expansion and R198 full-spectrum harvester expansion

Safety state:

- audit-only
- no Binance/network calls
- no env/config writes
- no lane mode changes
- no risk contract writes
- no order/test-order/protective/transfer/withdraw calls
- no live authorization, lane promotion, or signal-origin promotion
