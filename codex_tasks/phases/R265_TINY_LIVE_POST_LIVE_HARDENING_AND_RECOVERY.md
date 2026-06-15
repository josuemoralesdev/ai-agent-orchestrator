# R265 Tiny-Live Post-Live Hardening And Recovery

## Purpose

Inspect the R264 actual-submit/reconciliation ledger after any actual tiny-live
submit attempt and build a recovery/hardening packet.

## Required Inputs

- `logs/hammer_radar_forward/tiny_live_actual_submit_reconciliation.ndjson`
- latest R264 partial-success state, if any
- latest R264 submit/reconciliation order ids and statuses
- current operator dashboard state

## Required Behavior

- inspect actual submit and reconciliation records
- identify whether a partial-success state exists
- provide recovery command packets for operator review
- add dashboard recovery state
- add a re-entry lock so duplicate main submits remain blocked
- preserve all R264 idempotency evidence
- keep recovery explicit and manually gated

## Non-Negotiables

- no extra live order unless a separate exact recovery phrase exists
- no duplicate main submit
- no automatic cancellation or recovery order by default
- no Binance private/account/order calls during preview/tests
- no env/config/risk/lane/paper/performance/promotion mutation unless a future
  phase explicitly authorizes a bounded write
- no secret printing or persistence

## Expected Output

R265 should report:

- latest R264 status
- whether partial success is present
- which order roles submitted/reconciled
- operator recovery packet
- dashboard recovery state
- re-entry lock status
- exact next operator move
