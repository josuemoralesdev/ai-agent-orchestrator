# R109 First-Live Cockpit Sacred Button Hardening

Phase: R109

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R109 Adds

R109 hardens the existing R108 first-live operator approval cockpit. It keeps the same endpoints:

- `GET /operator/approval-cockpit`
- `GET /operator/approval-cockpit/state`
- `POST /operator/approval-cockpit/intent`

The cockpit now includes:

- a top safety banner: `FIRST LIVE COCKPIT`, `INTENT ONLY`, `NO ORDER CAN BE PLACED`, `R106 GATE AUTHORITY`
- a devil-red watchful-eye sacred button visual
- a large countdown panel with hourglass wording and depletion bar
- a compact sacred button state object in JSON
- a blocker hierarchy summary
- an operator path-to-press checklist
- richer simultaneous signal tags and shortened hashes with full values preserved in state

## What R109 Does Not Add

R109 does not add:

- live trading
- Binance order calls
- account or balance calls
- env flag changes
- approval-to-execution wiring
- Telegram approval-to-execution wiring
- a live order endpoint
- execution authority
- service restarts

## Sacred Button Semantics

The sacred button is a visual and intent-recording control only.

Its label is always one of:

- `SACRED BUTTON LOCKED`
- `RECORD INTENT ONLY`
- `EXPIRED`
- `BLOCKED BY R106`

The state endpoint reports:

- `can_place_order=false`
- `records_intent_only=true`
- `enabled=false` unless the intent-only prerequisites are satisfied

Pressing the enabled button can only call the existing intent endpoint. It cannot place an order.

## Devil-Red Watchful Eye Meaning

The devil-red watchful-eye visual is an operator warning symbol. It means the operator is at the final human-intent surface and must treat the action as serious, audited, and gated.

It is deliberately powerful visually, but powerless operationally. It does not bypass R106, does not arm execution, and does not change live flags.

## Why The Sacred Button Is Intent Only

R106 remains backend authority. The cockpit is not an execution surface because it:

- records only `OPERATOR_APPROVAL_COCKPIT_INTENT` ledger rows
- returns `live_ready=false`
- returns `execution_enabled_by_ui=false`
- returns `order_placed=false`
- returns `real_order_placed=false`
- returns `execution_attempted=false`
- returns `real_order_possible=false`
- exposes no order-submit path

## How To Eventually Make The Button Pressable

The operator path panel shows that all of the following must be true before the sacred button can record intent:

1. R102 final preflight is `READY`.
2. R104 tiny-live armed dry run is `READY_FOR_DRY_RUN`.
3. R105 protocol is `PROTOCOL_PREREQS_READY`.
4. R106 activation gate is `FIRST_LIVE_ACTIVATION_READY`.
5. The approval window is `OPEN`.
6. Candidate id, risk contract hash, and packet hash are present and match the R106 evidence.
7. The future execution-phase confirmation phrase remains a separate requirement.

Even then, this cockpit only records intent.

## Countdown And Window Behavior

The approval window is derived from R106 evidence and current candidate/hash availability. The UI displays:

- hourglass wording
- large minutes/seconds remaining
- window status
- depletion bar

When the window expires, the sacred button visibly locks and the backend rejects intent recording.

## Blocker Hierarchy

The JSON state includes `blocker_summary`:

- `primary_blockers`: top five high-level blockers
- `detailed_blocker_count`
- `final_preflight_blocker_count`
- `dry_run_blocker_count`
- `protocol_blocker_count`
- `activation_gate_blocker_count`

This reduces the wall of blockers while keeping detailed blockers available in the raw state.

## Safety Constraints

R109 preserves:

- no live orders
- no Binance order endpoint calls
- no account or balance calls
- no env edits
- no secret exposure
- no UI approval-to-execution wiring
- no Telegram approval-to-execution wiring
- no executable payload creation
- no live order endpoint
- paper/live separation
- R106 backend authority

## How This Prepares R110

R110 should be a final operator path review and readiness rehearsal. It should walk through the cockpit, verify every gate, confirm button state and blocker priority, validate operator comprehension, and prove that no execution path exists unless a later phase explicitly authorizes one.
