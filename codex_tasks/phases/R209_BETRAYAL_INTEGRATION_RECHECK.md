# R209 Betrayal Integration Recheck

## Purpose

Explicitly recheck how betrayal/inverse context should be integrated into current strategy, ranking, and readiness review surfaces without changing config or live state.

## Required Context

- Include the R80 `222m` aggregate betrayal primary candidate.
- Include the R80 `88m` aggregate betrayal watchlist candidate.
- Preserve R81 true inverse validation as required before promotion.
- Treat any R198/R208A `222m` full-spectrum capture as paper-only evidence to surface, not as live readiness.

## Safety

This phase must not:

- write env/config/lane/risk/registry/scoring/matrix config
- call Binance or any network
- place orders
- create executable payloads
- sign requests
- change live flags
- disable the kill switch
- set any lane `tiny_live`
- promote any signal origin or lane
- authorize live execution

## Expected Output

Produce a paper-only recheck that says whether betrayal context is absent, present but not integrated, or integrated into review surfaces, and what remains required before betrayal promotion.
