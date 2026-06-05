# R201 Anchor Outcome Deepening

Purpose: deepen R199 WMA/MA anchor outcome studies before any scoring or promotion review.

Required scope:

- Compare WMA200, MA200, and custom WMA periods across selected and discovered timeframes.
- Deepen outcome windows and sample-size reporting for anchor interactions.
- Map anchor + signal-origin confluence at candle level where local detector evidence supports it.
- Keep all output paper-only and preview/audit oriented.
- Produce candidate evidence for later scoring research only.

Required safety:

- no config writes
- no env writes or mutation
- no lane mode changes
- no signal-origin promotion
- no lane promotion
- no Binance/network calls
- no order/test-order/protective/transfer/withdraw calls
- no signed requests or executable payloads
- no live execution or live authorization
- no anchor-based position permission

Expected inputs:

- `logs/hammer_radar_forward/wma_ma_anchor_layer_preview.ndjson`
- `logs/hammer_radar_forward/candle_archive/*.ndjson`
- R197 pattern-family expansion records
- R189/R193 Three Black Crows detection/outcome records where available

Expected output:

- append-only anchor deepening ledger
- per-anchor/per-timeframe outcome comparisons
- anchor + signal-origin confluence summaries
- explicit sample-size and confidence limits
- safety object proving no config, network, order, promotion, or live action occurred

Confirmation phrase should be exact, paper-only, and no-write.
