# R82 Markov Regime Gate

## Purpose

R82 adds a read-only Markov-style regime gate for Hammer Radar strategy candidates. It classifies current local market regime from archived candles and attaches regime support, rejection, or neutral context to normal strategy candidates and betrayal/inverse candidates.

R82 is paper/operator evidence only. It does not execute trades, approve live trading, call Binance live/trading endpoints, expose secrets, edit env files, or restart services.

## Why R82 Follows R81.4

R80 through R81.3 built the betrayal evidence path:

- R80/R80.2 separated aggregate betrayal candidates from direction/entry-mode candidates.
- R81 added true inverse validation.
- R81.1 added a resolver.
- R81.2 added the candle archive bridge.
- R81.3 added runtime candle capture.

R81.4 fixed the unsafe timestamp alignment issue where old April shadow signals could be resolved from unrelated May candles. After that fix, latest safe evidence still showed true inverse validation pending, with resolved true inverse samples at zero.

R82 adds market regime context without replacing R81 true inverse validation or the normal 13m/44m promotion review path.

## Regime States

Initial R82 states:

- `BULL_TREND`
- `BEAR_TREND`
- `RANGE`
- `HIGH_VOLATILITY`
- `LOW_VOLATILITY`
- `TRANSITION`
- `INSUFFICIENT_DATA`

When local candles are missing or below the minimum sample, R82 returns `INSUFFICIENT_DATA` and does not fabricate confidence.

## Transition Logic

R82 reads local archive candles from:

```text
logs/hammer_radar_forward/candle_archive/{symbol}_{timeframe}.ndjson
```

It converts recent candles into deterministic micro states:

- `UP_STRONG`
- `UP_WEAK`
- `DOWN_STRONG`
- `DOWN_WEAK`
- `FLAT`
- `VOL_SPIKE`

It then builds transition counts and probabilities from chronological micro-state pairs. The final regime uses observable features:

- total close-to-close return
- average absolute return
- average candle range
- recent micro-state distribution
- transition matrix summary

No external ML dependency, network fetch, or Binance call is used.

## Normal Candidate Handling

R82 reads normal candidate rows from the existing strategy performance live-eligibility matrix. It focuses on the normal promotion context:

- `13m` long primary path when available
- `44m` long review/near-promotion path when available

Initial long/short gate logic:

- Long candidate in `BULL_TREND`: `REGIME_SUPPORTS_CANDIDATE`
- Long candidate in `BEAR_TREND`: `REGIME_REJECTS_CANDIDATE`
- Short candidate in `BEAR_TREND`: `REGIME_SUPPORTS_CANDIDATE`
- Short candidate in `BULL_TREND`: `REGIME_REJECTS_CANDIDATE`
- Range, transition, low volatility, high volatility, or insufficient data: neutral or pending

Regime support is not live eligibility.

## Betrayal Candidate Handling

R82 reads betrayal candidates from R80.2 and true inverse validation status from R81:

- `222m` aggregate betrayal primary candidate
- `88m` aggregate betrayal watchlist
- `55m` aggregate betrayal watchlist
- direction/entry-mode betrayal candidates if already surfaced by R80.2

Aggregate betrayal candidates do not have a validated direction split, so R82 marks them contextual/neutral and adds:

```text
aggregate_betrayal_direction_context_only
```

If true inverse validation is not validated, R82 adds:

```text
true_inverse_validation_pending
```

R82 must not validate betrayal candidates merely because regime context looks favorable.

## Gate Statuses

R82 uses:

- `REGIME_SUPPORTS_CANDIDATE`
- `REGIME_REJECTS_CANDIDATE`
- `REGIME_NEUTRAL_OR_INSUFFICIENT_DATA`
- `REGIME_PENDING_MORE_CANDLES`

`REGIME_SUPPORTS_CANDIDATE` is a context label only. It does not bypass R81 true inverse validation, Miro Fish, funding, protective order, exact operator approval, or live execution gates.

## No-Live Guarantees

R82 payloads keep:

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
order_payload_created=false
network_allowed=false
secrets_shown=false
```

## Smoke Commands

CLI:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  markov-regime-gate
```

Related betrayal evidence:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-inverse-validation
```

Candle archive context:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-candle-archive --limit 20
```

API when the local service is already running:

```text
curl -s http://127.0.0.1:8015/strategy-performance/markov-regime-gate | jq '
{
  status,
  phase,
  execution_mode,
  regime_summary,
  normal_candidate_regime_gates,
  betrayal_candidate_regime_gates,
  live_execution_enabled,
  allow_live_orders,
  global_kill_switch,
  order_placed,
  real_order_placed,
  execution_attempted,
  network_allowed,
  secrets_shown
}'
```

## Next Phase Recommendation

R83 should add the Miro Fish Quality Gate. It should evaluate signal quality and structural setup quality after R82 regime context, while preserving the same rule: regime or quality support is evidence only, not live execution permission.
