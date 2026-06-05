# R201 Anchor Outcome Deepening

R201 deepens the R199 WMA/MA anchor preview into a paper-only outcome research surface. It reuses local candle archives and R199 anchor classification, extends mapped outcome windows to `1`, `3`, `5`, `10`, `21`, `34`, and `55`, separates sample quality, and overlays recorded signal-origin summaries for confluence review.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  anchor-outcome-deepening \
  --symbol BTCUSDT
```

Rejected confirmation smoke:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  anchor-outcome-deepening \
  --record-deepening \
  --confirm-anchor-outcome-deepening "wrong"
```

Record deepening only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  anchor-outcome-deepening \
  --symbol BTCUSDT \
  --record-deepening \
  --confirm-anchor-outcome-deepening "I CONFIRM ANCHOR OUTCOME DEEPENING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Scope

- Reads the latest R199 WMA/MA anchor preview record when present.
- Recomputes local anchor events from `logs/hammer_radar_forward/candle_archive/` through R199 helpers.
- Keeps R199 anchor defaults: `SMA200`, `WMA200`, `custom_wma`, and custom WMA periods `13`, `21`, `34`, `55`, `89`, `144`, `200`, `233`, `377`, `610`, and `888`.
- Maps anchor interactions across longer paper-only windows.
- Ranks per-anchor, per-timeframe, and summary-level signal-origin confluence candidates.
- Marks confluence as `summary_level_only` unless exact local event timestamps are available and matched.

## Safety State

R201 does not write env/config/risk/lane/registry/scoring/matrix state, call Binance/network, create executable or signed payloads, place orders, transfer, withdraw, promote signal origins, promote lanes, change live flags, disable kill switches, or authorize anchor-based live trading.

The output safety object keeps:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `network_allowed=false`
- `config_written=false`
- `env_mutated=false`
- `paper_live_separation_intact=true`
- `anchor_live_authorized=false`
- `anchor_position_permission_created=false`

## Ledger

Optional confirmed records append to:

```text
logs/hammer_radar_forward/anchor_outcome_deepening.ndjson
```

## Next Work

- R202 should map detector-backed pattern-family outcomes without config writes, Binance/network calls, or live execution.
- R203 should combine R201 anchor candidates, R202 pattern outcomes, signal-origin detections, and lane rankings into a paper-only confluence matrix.
