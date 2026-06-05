# R202 Pattern Outcome Mapping Family

## Objective

Map paper outcomes for R197/R200 detector-backed pattern-family signal origins:

- `three_white_soldiers`
- `bearish_engulfing`
- `bullish_engulfing`
- `exhaustion_wick`

## Scope

- Read local R197 pattern-family detector records.
- Read local candle archives only.
- Map detector occurrences to future paper outcome windows.
- Summarize results by signal origin, timeframe, direction, strict/loose mode, and window.
- Produce review recommendations for later Keter and lane-matrix scoring.

## Non-Negotiable Safety

- No config writes.
- No registry/scoring/matrix mutation.
- No signal-origin promotion.
- No lane promotion.
- No live execution.
- No Binance/network calls.
- No order/test-order/protective/transfer/withdraw calls.
- No executable or signed payloads.
- No env mutation.
- No secrets.

## Expected Output

- Preview by default.
- Optional append-only outcome mapping ledger after exact confirmation.
- Safety object proving no env/config/network/order/live actions occurred.
- Remaining gaps for `breakdown_retest` and `breakout_retest` until retest structure exists.
