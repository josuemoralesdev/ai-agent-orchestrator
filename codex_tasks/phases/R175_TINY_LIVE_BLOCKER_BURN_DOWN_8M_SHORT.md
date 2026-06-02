# R175 Tiny-Live Blocker Burn-Down 8m Short

## Phase

R175 Tiny-Live Blocker Burn-Down 8m Short

## Classification

- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk: MEDIUM

## Purpose

Produce a compact blocker burn-down for the BTCUSDT 8m short tiny-live path after R174 syncs role-specific account-read funding evidence.

Target family:

- `BTCUSDT|8m|short|ladder_close_50_618`

## Required Blocker Groups

The burn-down must include:

- funding
- fresh captures
- risk contract
- lane mode
- protective policy
- operator approval
- live flags

## Safety Boundary

R175 is diagnostic/audit only.

It must not:

- write env files
- mutate config files
- write risk-contract config
- change lane modes
- set short tiny-live
- call Binance
- call order/test-order/protective endpoints
- transfer or withdraw
- create executable payloads
- create signed trading/order requests
- enable live execution
- disable the kill switch
- place orders
- expose secrets

## Expected Inputs

Reuse existing local surfaces where possible:

- R174 funding gate role-specific sync
- R173 account-read migration verification
- R164/R167 readonly balance records
- R158 short evidence recheck packet
- R162 short risk-contract apply review
- lane controls
- protective policy review surfaces
- global live/readiness flags

## Expected Output

Return a compact JSON report with:

- target family and current mode
- blocker group status
- exact next evidence/action needed for each blocker
- safe operator sequence
- do-not-run-yet list
- safety object proving no env/config/live/order/Binance mutation

## Validation

Run focused tests for the R175 module and CLI, plus related R174/R173/R158/R162 tests as scope warrants.
