# R182 Signal Origin Registry and Pattern Feed Expansion

## Phase Classification

Primary: WIRING / INTEGRATION
Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY
Duplicate risk: MEDIUM

## Purpose

Create a paper-only signal origin registry that explains which pattern families contribute to each candidate lane and expands tagging/scoring coverage for:

- hammer
- three black crows
- engulfing
- RSI divergence
- golden pocket rejection

## Scope

R182 should:

- read local Hammer Radar signal, scan, paper watch, and R180/R181 evidence ledgers
- attach source/origin metadata to paper candidate review output
- expose pattern family counts and per-lane source pressure
- keep all scoring diagnostic and paper-only
- recommend which pattern families need more paper evidence

## Non-Negotiable Safety

R182 must not:

- place orders
- call Binance
- call order/test-order/protective endpoints
- create executable payloads
- create signed requests
- write env files
- write config files
- write lane controls
- write risk-contract config
- change lane modes
- set any lane `tiny_live`
- disable the kill switch
- enable live execution
- transfer or withdraw
- print secrets

## Expected Surfaces

Suggested module:

- `src/app/hammer_radar/operator/signal_origin_registry.py`

Suggested CLI:

- `signal-origin-registry`

Suggested ledger:

- `logs/hammer_radar_forward/signal_origin_registry.ndjson`

All recording must be append-only and require an exact paper-only confirmation phrase.
