# R203 Anchor Signal Confluence Matrix

R203 builds a paper-only confluence matrix from recorded local evidence:

- R201 anchor outcome deepening
- R205 pattern lane matrix review
- R204 pattern Keter rescoring
- R192/R195 crow and hammer lane references

The matrix separates `event_level`, `summary_level`, and `none` confluence. Current R201/R205/R204 ledgers provide timeframe/source overlap but not exact shared candle timestamps, so present candidates are expected to be summary-level until R207 performs timestamp matching.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  anchor-signal-confluence-matrix
```

Record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  anchor-signal-confluence-matrix \
  --record-matrix \
  --confirm-anchor-signal-confluence "I CONFIRM ANCHOR SIGNAL CONFLUENCE MATRIX RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Safety

R203 is audit-only. It does not write env/config/risk/lane/registry/scoring/matrix config, call Binance/network, create payloads, sign requests, place orders, transfer, withdraw, change live flags, disable the kill switch, promote signal origins or lanes, authorize live execution, or create position permission.

Confluence scores are paper evidence only and must not be treated as live readiness or live authorization.

## Current Interpretation

Best paper-only candidates should come from overlaps between high-scoring R205 lane/origin pairs and R201 anchor interactions, especially BTCUSDT 8m short rows involving `hammer_wick_reversal`, `bearish_engulfing`, and `three_black_crows`.

Summary-level confluence is intentionally penalized versus event-level confluence because exact anchor-event and signal-origin timestamps have not yet been matched.

## Follow-Up

R207 should perform exact event-level timestamp/candle matching between anchor events and signal-origin detections without config writes, live execution, Binance/network calls, or order actions.
