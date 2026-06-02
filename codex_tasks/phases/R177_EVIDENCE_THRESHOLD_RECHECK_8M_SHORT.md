# R177 Evidence Threshold Recheck for BTCUSDT 8m Short

## Trigger

Run R177 only after R176 reports:

- `capture_count.fresh_capture_count >= 10`
- `capture_count.threshold_met=true`
- `threshold_status=CAPTURE_THRESHOLD_MET`

## Purpose

R177 should rerun the R158 evidence readiness path for `BTCUSDT|8m|short|ladder_close_50_618` after the R157/R176 capture threshold is met.

It should decide whether the short risk-contract apply review can proceed in a future phase.

## Safety

R177 must remain non-executing:

- no live execution
- no orders
- no Binance order/test/protective/transfer/withdraw calls
- no config writes by default
- no env writes
- no lane mode changes
- no short `tiny_live` promotion
- no risk-contract config writes by default
- no payload creation
- no signed requests
- no kill-switch disable

## Expected Inputs

- `logs/hammer_radar_forward/short_paper_evidence_capture.ndjson`
- `logs/hammer_radar_forward/short_paper_evidence_capture_heartbeats.ndjson`
- `logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson`
- existing R158 short evidence recheck packet builder
- existing R162 risk-contract apply review surfaces

## Expected Output

R177 should report:

- current R176 capture threshold truth
- R158 evidence readiness result
- whether risk-contract apply review remains blocked
- the next safe operator move
- the next safe engineering move
- explicit no-live safety flags

## Default Decision

If any required evidence is missing, stale, inconsistent, or below threshold, R177 must remain blocked and recommend returning to the R157/R176 watcher flow.
