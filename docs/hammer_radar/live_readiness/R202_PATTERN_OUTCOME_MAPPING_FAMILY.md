# R202 Pattern Outcome Mapping Family

R202 maps detector-backed R197 candle-pattern family detections to future local candle windows as a paper-only audit surface. It uses local `candle_archive` OHLC only, reconstructs detector events with the existing R197 detector functions, and summarizes long/short favorable behavior by origin, timeframe, mode, and confidence.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-outcome-mapping-family \
  --symbol BTCUSDT
```

Rejected confirmation smoke:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-outcome-mapping-family \
  --record-mapping \
  --confirm-pattern-outcome-family "wrong"
```

Record mapping only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-outcome-mapping-family \
  --symbol BTCUSDT \
  --record-mapping \
  --confirm-pattern-outcome-family "I CONFIRM PATTERN OUTCOME MAPPING FAMILY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Scope

- Outcome-mapped origins: `three_white_soldiers`, `bearish_engulfing`, `bullish_engulfing`, and `exhaustion_wick`.
- Registry-only blocked origins: `breakdown_retest` and `breakout_retest`.
- Outcome windows: `1`, `3`, `5`, `10`, `21`, `34`, and `55` candles.
- Long contexts treat positive close return and upside MFE as favorable.
- Short contexts treat negative close return and downside MFE as favorable.
- Retest origins remain blocked until a local retest-structure detector exists.

## Safety State

R202 does not write env/config/risk/lane/registry/scoring/matrix state, call Binance/network, create executable or signed payloads, place orders, transfer, withdraw, promote signal origins, promote lanes, change live flags, disable kill switches, write lane modes, or authorize pattern-family live trading.

The output safety object keeps:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `network_allowed=false`
- `config_written=false`
- `env_mutated=false`
- `paper_live_separation_intact=true`
- `pattern_family_live_authorized=false`

## Ledger

Optional confirmed records append to:

```text
logs/hammer_radar_forward/pattern_outcome_mapping_family.ndjson
```

## Next Work

- R203 should combine R201 anchor outcomes with R202 pattern outcomes in a paper-only anchor x signal-origin confluence matrix.
- R204 should feed R202 outcome rankings into pattern-family Keter rescoring without config writes, Binance/network calls, live execution, or promotion.
