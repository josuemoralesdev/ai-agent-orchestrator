# R80 Betrayal Strategy Audit

## Purpose

R80 adds a paper/shadow-only betrayal strategy audit layer for Hammer Radar. It ranks consistently losing strategy families as possible inverse candidates while preserving the existing normal strategy promotion system.

R80 does not place orders, enable live execution, call Binance, create signed payloads, or edit env files.

## Why R80 Before Markov

R80 was chosen before a Markov Regime Gate because the current paper data already shows unusually strong inverse evidence on some blocked/context timeframes. Capturing that evidence now gives the later regime gate better inputs without changing live execution readiness.

## Current Evidence

Recent inspection showed:

- `222m`: original sample count `48`, original win rate `12.5%`, average pnl `-0.2944%`, total pnl `-14.1309%`, naive inverse win rate `87.5%`, naive inverse total pnl `+14.1309%`.
- `88m`: original sample count `90`, original win rate `36.67%`, average pnl `-0.0178%`, total pnl `-1.5995%`, naive inverse win rate `63.33%`, naive inverse total pnl `+1.5995%`.

Under R80 rules, matching `222m` evidence is a `BETRAYAL_PRIMARY_CANDIDATE`; matching `88m` evidence is a `BETRAYAL_WATCHLIST`.

## Naive Inverse Metrics

R80 computes:

```text
betrayal_win_rate_pct = 100 - original_win_rate_pct
betrayal_avg_pnl_pct = -original_avg_pnl_pct
betrayal_total_pnl_pct = -original_total_pnl_pct
```

These are audit evidence only. True inverse paper outcomes must be tracked before live eligibility.

## Classification Rules

`BETRAYAL_PRIMARY_CANDIDATE`:

- sample count >= `30`
- original win rate <= `25%`
- original average pnl < `0`
- original total pnl < `0`
- betrayal win rate >= `75%`
- betrayal total pnl > `0`

`BETRAYAL_WATCHLIST`:

- sample count >= `30`
- original win rate < `40%`
- original average pnl < `0`
- original total pnl < `0`
- betrayal win rate >= `60%`
- betrayal total pnl > `0`

Rejected or not betrayal:

- sample count below minimum
- original total pnl is positive
- original average pnl is positive
- inverse metrics are weak
- candidate fails thresholds

## Normal Strategy Promotion Is Preserved

R80 does not replace the existing promotion-ready `BTCUSDT|13m|long|ladder_close_50_618` path. It reads the same performance rows and adds an inverse audit view. Normal long promotion rules, active timeframe review, rehearsal, test order, protective readiness, final gate, and manual arming rules remain unchanged.

## No-Order Guarantees

R80 payloads keep:

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

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect betrayal-strategy-audit

curl --max-time 5 -s http://127.0.0.1:8015/strategy-performance/betrayal-audit \
  | jq '{
    status,
    phase,
    primary_candidates,
    watchlist_candidates,
    order_placed,
    real_order_placed,
    execution_attempted,
    order_payload_created,
    network_allowed,
    secrets_shown
  }'
```

## Next Phase Recommendation

R81 should add true inverse paper outcome validation and link it to existing `betrayal_shadow_outcomes` records. Markov Regime Gate should follow before any scaling decision, so betrayal candidates are only considered in regimes where inverse behavior is repeatable.
