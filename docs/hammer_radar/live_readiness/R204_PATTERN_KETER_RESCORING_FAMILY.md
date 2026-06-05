# R204 Pattern Keter Rescoring Family

R204 feeds recorded R202 pattern-family outcome evidence and R200 detector-family feedback into a paper-only Keter rescoring surface.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-keter-rescoring-family
```

Rejected confirmation smoke:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-keter-rescoring-family \
  --record-rescore \
  --confirm-pattern-keter-family "wrong"
```

Record rescore only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  pattern-keter-rescoring-family \
  --record-rescore \
  --confirm-pattern-keter-family "I CONFIRM PATTERN KETER RESCORING FAMILY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Scope

Scored pattern origins:

- `three_white_soldiers`
- `bearish_engulfing`
- `bullish_engulfing`
- `exhaustion_wick`

Blocked registry-only origins:

- `breakdown_retest`
- `breakout_retest`

R204 separates detector feedback from outcome evidence. It rewards detector availability, detection volume, mapped outcome depth, favorable directional behavior, timeframe coverage, and anchor overlay readiness. It penalizes mixed directional bias, high failure risk, adverse move dominance, and any live authorization breach.

## Output

The operator packet includes:

- target scope for BTCUSDT pattern origins
- input summary from R202/R200 ledgers
- per-origin Keter scorecards
- paper-only pattern rankings
- reference comparison against `hammer_wick_reversal` and `three_black_crows` when local ledgers contain those scores
- lane matrix recommendations
- anchor confluence recommendations
- explicit do-not-run list
- safety object proving no env/config/live/order/network mutation

## Safety State

R204 is scoring/audit only. It does not write env/config/risk/lane/registry/scoring/matrix state, call Binance/network, create executable or signed payloads, place orders, transfer, withdraw, promote signal origins, promote lanes, change live flags, disable kill switches, create pattern live permissions, infer live readiness, or authorize pattern-family live trading.

The output safety object keeps:

- `env_written=false`
- `config_written=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `network_allowed=false`
- `paper_live_separation_intact=true`
- `signal_origin_promoted=false`
- `lane_promoted=false`
- `pattern_family_live_authorized=false`
- `anchor_live_authorized=false`

## Ledger

Optional confirmed records append to:

```text
logs/hammer_radar_forward/pattern_keter_rescoring_family.ndjson
```

## Next Work

- R203 should build the anchor x signal-origin confluence matrix without config writes or live execution.
- R205 should build the pattern-origin lane matrix review from R204 scores without config writes, Binance/network calls, live execution, or promotion.
