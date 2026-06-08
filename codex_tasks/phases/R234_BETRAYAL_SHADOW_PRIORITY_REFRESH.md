# R234 Betrayal Shadow Priority Refresh

## Purpose

Refresh betrayal/inverse shadow context after R230/R233 so active betrayal evidence stays visible while the official protected tiny-live path continues waiting for 10/10.

## Scope

- Read latest R230 betrayal upstream emitter entry-mode contract.
- Read latest R233 capture priority rebalance.
- Read latest R229, R227, R226, R225, R215-R230 betrayal context where present.
- Preserve 222m and 88m inverse evidence when present.
- Report whether a future betrayal contract smoke should run next.
- Keep all betrayal rows context-only and paper-only.

## Non-Negotiable Safety

R234 must not:

- write configs, env files, lane controls, registry, scoring, matrix, scheduler, fisherman, or risk-contract config
- rewrite historical ledgers
- append normalized betrayal source rows
- call Binance or any network
- create order payloads
- sign requests
- place orders
- transfer or withdraw
- enable live execution
- disable the kill switch
- set any lane `tiny_live`
- promote betrayal, signal origins, or lanes
- infer tiny-live readiness or live readiness from betrayal context

## Expected Output

- Betrayal/inverse shadow priority summary.
- 222m and 88m preservation status.
- Resolver/future-contract smoke readiness context.
- Blockers proving betrayal remains shadow-only.
- Recommended next engineering move.

## Validation

- Focused tests proving preview-only behavior.
- Safety assertions for no config/env/network/order/live mutation.
- Smoke command with local logs only.
