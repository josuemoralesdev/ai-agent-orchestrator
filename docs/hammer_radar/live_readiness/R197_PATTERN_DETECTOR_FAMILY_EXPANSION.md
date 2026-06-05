# R197 Pattern Detector Family Expansion

R197 adds a paper-only detector family preview for registered signal origins that R196 found without detectors.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-detector-family-expansion \
  --symbol BTCUSDT \
  --mode both
```

Rejected confirmation smoke:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-detector-family-expansion \
  --record-expansion \
  --confirm-pattern-family-expansion "wrong"
```

Record expansion review:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-detector-family-expansion \
  --symbol BTCUSDT \
  --mode both \
  --record-expansion \
  --confirm-pattern-family-expansion "I CONFIRM PATTERN DETECTOR FAMILY EXPANSION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledgers:

```text
logs/hammer_radar_forward/pattern_detector_family_expansion.ndjson
logs/hammer_radar_forward/pattern_family_paper_tags.ndjson
```

The `pattern_family_paper_tags.ndjson` path is reported for future sync continuity, but R197 does not write tag records. It previews tag count only and records the expansion review ledger after exact confirmation.

Detector family:

- `three_white_soldiers`: long, strict and loose-preview local candle detector
- `bearish_engulfing`: short, strict and loose-preview local candle detector
- `bullish_engulfing`: long, strict and loose-preview local candle detector
- `exhaustion_wick`: long/short by wick location, strict and loose-preview local candle detector
- `breakdown_retest`: registry-only preview, no fake retest detections
- `breakout_retest`: registry-only preview, no fake retest detections

R197 reuses:

- `operator.local_candle_feed_adapter.resolve_local_candle_feed_path`
- `operator.local_candle_feed_adapter.load_local_candle_feed`
- `operator.local_candle_feed_adapter.normalize_local_candle_feed`
- `operator.local_candle_feed_adapter.validate_normalized_candle_feed`
- the R185/R189 strict/loose detector and paper-only tag model

Default scope:

```text
BTCUSDT
4m, 8m, 13m, 22m, 44m, 55m, 88m, 222m, 444m, 666m, 888m, 4H, 13H, 13D
```

Safety state:

- paper/detector preview only
- no Binance/network calls
- no env/config/lane/risk-contract writes
- no registry/scoring/matrix config writes
- no lane mode changes
- no tiny-live promotion
- no signal-origin promotion
- no order/test-order/protective/transfer/withdraw calls
- no signed requests or executable payloads
- no live authorization

R197 prepares R200, which should sync pattern-family detection evidence into registry/Keter/lane-matrix review surfaces without config writes, promotion, Binance/network calls, or live execution.
