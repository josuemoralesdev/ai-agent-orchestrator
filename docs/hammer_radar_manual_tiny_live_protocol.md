# Hammer Radar Manual Tiny-Live Protocol

## Purpose

Manual tiny-live testing only. No automated trading.

This protocol is for manual tiny-live testing only. Hammer Radar does not automate live trading, does not place orders, and does not call Binance live execution. All real trade actions, if any, are performed manually by the human operator outside the app.

## Scope

- Market: BTCUSDT only for now.
- Max initial position: 44 USDT notional.
- Max leverage: 3x.
- Preferred leverage: 2x.
- Margin: isolated only.
- App mode: paper/manual-only.

## Candidate Requirement

The candidate must be a fresh `ELIGIBLE_TINY_LIVE` candidate from `live-checklist` or the local approval UI.

- Freshness: candidate age must be <= 30 minutes.
- First live test should not override freshness.
- Direction: long-only by default unless `allow-short` has been intentionally enabled and noted.
- RSI rule: neutral preferred.
- Oversold is not allowed for the first live test.
- Divergence: bullish confirmed is preferred for a long.

The candidate must have:

- entry
- stop
- take profit
- `capped_max_position_size_usd <= 44`
- `suggested_leverage <= 3`

## Required Before Entry

- Log the decision through the UI/API.
- Screenshot the candidate card.
- Screenshot the exchange order preview.
- Confirm max daily loss has not been breached.
- Confirm isolated margin.
- Confirm predefined stop.
- Confirm predefined take profit.

## Required During Entry

- Use isolated margin only.
- Set the stop before or immediately after entry.
- Set the take profit.
- Do not change position size upward after entry.

## Required After Exit

- Screenshot the exit.
- Record the result with `log-manual-outcome` or `/manual-outcomes`.
- Compare the paper signal against the manual trade.
- Complete post-trade review before considering another manual trade.

## Hard Daily Stop

Stop manual live trading after one losing live trade or 5 USDT max loss, whichever comes first.

## First Week Rule

Max one manual tiny-live trade per day.

## Forbidden

- No martingale.
- No revenge trade.
- No increasing size after loss.
- No trading `FORBIDDEN` candidates.
- No trading expired candidates.
- No trading without a stop.
- No 50x, 100x, or 150x leverage.
- No automatic exchange execution.

## Local Logging

Log intent before entry:

```bash
http://127.0.0.1:8015/ui
```

Log outcome after exit:

```bash
HAMMER_RADAR_LOG_DIR=/path/to/logs/hammer_radar_forward \
  .venv/bin/python -m src.app.hammer_radar.operator.inspect log-manual-outcome \
  --signal-id "..." \
  --result win \
  --entry-price 100 \
  --exit-price 101 \
  --position-usd 44 \
  --leverage 2 \
  --pnl-usd 0.44 \
  --pnl-pct 1.0 \
  --notes "manual review"
```

Review outcomes:

```bash
HAMMER_RADAR_LOG_DIR=/path/to/logs/hammer_radar_forward \
  .venv/bin/python -m src.app.hammer_radar.operator.inspect manual-outcomes
```

All records include `live_execution_enabled=false` and `order_placed=false`.
