# R204 Pattern Keter Rescoring Family

## Purpose

Feed R202 pattern-family outcome mapping into Keter scoring review for detector-backed candle-pattern origins.

## Inputs

- `logs/hammer_radar_forward/pattern_outcome_mapping_family.ndjson`
- R202 preview output when no recorded mapping exists
- Existing Keter signal-origin scoring concepts
- Existing pattern-family feedback from R200

## Scope

- Review `three_white_soldiers`, `bearish_engulfing`, `bullish_engulfing`, and `exhaustion_wick`.
- Keep `breakdown_retest` and `breakout_retest` registry-only until retest-structure detectors exist.
- Compare R202 outcome rankings, favorable close rates, simple success/failure rates, MFE/MAE balance, sample count, and confidence.
- Produce paper-only Keter rescoring recommendations.

## Safety

R204 must not:

- write env files
- write config files
- write registry, scoring, matrix, risk-contract, or lane config
- promote signal origins
- promote lanes
- create pattern-based entry permission
- create order or protective payloads
- sign requests
- call Binance or any network
- call order, test-order, transfer, or withdraw endpoints
- disable the kill switch
- enable live execution
- set any lane `tiny_live`
- place orders

## Expected Output

- Pattern-family Keter feedback projection.
- Explicit `paper_only=true` and `live_authorized=false` on all recommendation rows.
- Registry-only blockers preserved for retest origins.
- Next operator/engineering move recommendations only, with no config writes.
