# R187 Local Candle Feed Capture Preview No Binance

## Purpose

Determine how Hammer Radar can create or consume a local OHLC candle feed for pattern detectors such as Three Black Crows without calling Binance and without enabling live execution.

## Scope

- Inspect existing local market-data, candle, scanner, signal, and paper-harvester ledgers.
- Determine whether any existing local records contain valid `open`, `high`, `low`, `close`, `symbol`, `timeframe`, and timestamp fields.
- If valid local OHLC exists, define a read-only adapter path for detector consumption.
- If valid local OHLC does not exist, preview a local-only capture design that can be implemented in a later phase.

## Non-Negotiables

- No Binance calls.
- No live execution.
- No orders or test orders.
- No order payloads.
- No executable payloads.
- No signed requests.
- No transfer or withdraw calls.
- No env writes.
- No config writes.
- No lane config writes.
- No risk-contract config writes.
- No lane mode changes.
- No tiny-live arming.
- No signal-origin promotion.
- No lane promotion.
- No secrets printed.

## Expected Output

- A diagnostic report of existing local candle/OHLC availability.
- A clear decision on whether a valid local OHLC feed already exists.
- A proposed local-only feed file shape if a new feed is needed.
- Safety flags proving no live, Binance, order, env, or config action occurred.
