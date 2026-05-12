# R78 Rehearsal / Test-Order / Protective Readiness

## Purpose

R78 verifies whether the funded-ready Hammer Radar first-live chain can progress
from exact intent to rehearsal, test-order validation, and protective
stop-loss/take-profit readiness without placing a real order.

## What R78 Proves

- The selected chain has or still needs LIVE APPROVE and LIVE INTENT.
- R53 rehearsal readiness is present or is the next manual step.
- Test-order validation is present or is the next manual step.
- Protective stop-loss and take-profit readiness is present or is the next
  manual step.
- Naked entry remains blocked.
- The final manual live gate is still required.

## What R78 Does Not Prove

- It does not place an order.
- It does not enable live execution.
- It does not call Binance live order endpoints.
- It does not fund the account.
- It does not replace the final protected live gate.

## Preconditions

- R76 returned READY_TO_FUND before funding.
- R77 returns READY_AFTER_FUNDING if funds are already present.
- The exact candidate chain is selected and fresh.
- The exact chain requires approval plus intent before rehearsal.

## Commands

1. `FIRST LIVE NEXT`
2. `LIVE APPROVE <signal_id>`
3. `FIRST LIVE NEXT`
4. `LIVE INTENT <signal_id>`
5. `FIRST LIVE NEXT`
6. `LIVE REHEARSAL <intent_id>`
7. `LIVE REHEARSAL READINESS`
8. `FIRST LIVE TEST ORDER`
9. `FIRST LIVE PROTECTIVE CHECK`
10. `LIVE PROTECTIVE READINESS`

API:

- `GET /live/rehearsal-readiness/status`
- `GET /live/rehearsal-readiness/runbook`
- `POST /live/rehearsal-readiness/check`

## Safety

- R78 is `R78_READINESS_ONLY`.
- No real orders.
- No naked entry.
- Protective orders are required before live entry.
- Final manual gate remains required.
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`

## Rollback

- Keep `HAMMER_LIVE_EXECUTION_ENABLED=false`.
- Keep `HAMMER_ALLOW_LIVE_ORDERS=false`.
- Keep `HAMMER_GLOBAL_KILL_SWITCH=true`.
- Do not restart services automatically.
- Do not attempt a live order until the final protected gate passes.
