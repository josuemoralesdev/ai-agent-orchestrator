# R200 Pattern Family Feedback Sync

R200 syncs recorded R197 pattern-family detector evidence into signal-origin review surfaces. It is feedback/audit only and does not mutate registry, Keter scoring, lane matrix, risk-contract, lane, or env config.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-family-feedback-sync
```

Rejected confirmation smoke:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-family-feedback-sync \
  --record-feedback \
  --confirm-pattern-family-feedback-sync "wrong"
```

Record feedback sync only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-family-feedback-sync \
  --record-feedback \
  --confirm-pattern-family-feedback-sync "I CONFIRM PATTERN FAMILY FEEDBACK SYNC RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/pattern_family_feedback_sync.ndjson
```

Inputs:

- `logs/hammer_radar_forward/pattern_detector_family_expansion.ndjson`
- `logs/hammer_radar_forward/wma_ma_anchor_layer_preview.ndjson` when available
- existing registry, Keter, and lane-matrix review concepts from R182/R183/R184/R190

R200 keeps `breakdown_retest` and `breakout_retest` registry-only until a swing/retest structure detector exists. It marks detector-backed origins as ready for review, Keter rerun, lane-matrix rerun, and future paper outcome mapping:

- `three_white_soldiers`
- `bearish_engulfing`
- `bullish_engulfing`
- `exhaustion_wick`

Safety state:

- no Binance/network calls
- no env/config/risk/lane/registry/scoring/matrix writes
- no order, test-order, protective, transfer, or withdraw calls
- no signed requests or executable payloads
- no live flag changes
- no kill-switch disable
- no signal-origin promotion
- no lane promotion
- no pattern-family or anchor live authorization

Next work:

- R201 should deepen WMA/MA anchor outcome studies.
- R202 should map paper outcomes for the detector-backed pattern family without config writes, Binance/network calls, or live execution.
