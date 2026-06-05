# R197 Pattern Detector Family Expansion

Purpose: build or reuse paper-only detector family paths for registered signal origins that R196 flags as detector gaps.

Target origins:

- `three_white_soldiers`
- `bearish_engulfing`
- `bullish_engulfing`
- `exhaustion_wick`

Rules:

- paper-only
- local logs/candle feeds only
- no live execution
- no Binance/network calls
- no order/test-order/protective/transfer/withdraw calls
- no env writes
- no config writes
- no lane mode changes
- no signal-origin promotion
- no lane promotion

Expected output:

- detector preview modules or reused detector family adapters
- focused tests proving no network/order/live/config mutation
- operator CLI preview and optional append-only recording if needed
