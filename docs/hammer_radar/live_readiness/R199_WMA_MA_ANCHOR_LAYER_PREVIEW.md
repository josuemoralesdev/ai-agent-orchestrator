# R199 WMA / MA Anchor Layer Preview

R199 adds a paper-only research preview for moving-average anchor context. It reads local candle archives only, computes MA200/WMA200 plus custom WMA periods, classifies price interactions with those anchors, maps interactions to future candle windows, and produces candidate rankings for later paper scoring research.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  wma-ma-anchor-layer-preview \
  --symbol BTCUSDT
```

Record preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  wma-ma-anchor-layer-preview \
  --symbol BTCUSDT \
  --record-preview \
  --confirm-wma-ma-anchor-preview "I CONFIRM WMA MA ANCHOR LAYER PREVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Scope

- Discover local candle archives under `logs/hammer_radar_forward/candle_archive/`.
- Include explicit target timeframes `4m`, `8m`, `13m`, `22m`, `44m`, `55m`, `88m`, `222m`, `444m`, `666m`, `888m`, `4H`, `13H`, and `13D`.
- Compute `SMA200`, `WMA200`, and `custom_wma` periods `13`, `21`, `34`, `55`, `89`, `144`, `200`, `233`, `377`, `610`, and `888` when enough candles exist.
- Classify touch, near-touch, rejection, cross, reclaim, loss, and distance from anchor.
- Map anchor events to 1, 3, 5, 10, and 21 future candle windows.
- Overlay recorded detector-family and Three Black Crows evidence as preview-only context.

## Safety State

R199 is research/audit only. It does not write env/config/risk/lane state, call Binance/network, create executable or signed payloads, place orders, transfer, withdraw, promote signal origins, promote lanes, change live flags, disable kill switches, or authorize anchor-based live trading.

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

Optional confirmed preview records append to:

```text
logs/hammer_radar_forward/wma_ma_anchor_layer_preview.ndjson
```

## Next Work

- R200 should sync R197 pattern-family evidence into paper-only feedback surfaces.
- R201 should deepen WMA/MA anchor outcome studies and candle-level anchor + signal-origin confluence without config writes, Binance/network calls, or live execution.
