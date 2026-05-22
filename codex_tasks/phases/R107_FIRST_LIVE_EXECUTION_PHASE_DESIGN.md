# R107 First-Live Execution Phase Design

Phase: R107

Status: DRAFT TASK ONLY

Branch: `r107-first-live-execution-phase-design`

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

Assigned agents:
- builder
- index
- qa
- security

## Main Objective

Design the first-live execution phase requirements after R106. This task does not implement execution behavior and does not authorize order placement.

## Non-Execution Rule

R107 is design only unless the user separately and explicitly authorizes execution-phase implementation in a future turn. No live order placement may occur from this draft task.

## Required Preconditions From R106

Before any execution-phase work can be considered:

- R102 final live preflight must report `READY`.
- R103 Telegram final approval intent must be present, accepted, and matching.
- R104 tiny-live armed dry run must report `READY_FOR_DRY_RUN`.
- R105 one tiny live order protocol must report `PROTOCOL_PREREQS_READY`.
- R106 first-live activation gate must report `FIRST_LIVE_ACTIVATION_READY`.
- `FIRST_LIVE_ACTIVATION_READY` must be fresh and tied to the same candidate/hash tuple.
- No duplicate readiness source conflict may exist.
- Paper/live separation must be intact.

If R106 reports `FIRST_LIVE_BLOCKED`, execution-phase work is blocked.

## Candidate / Hash / Confirmation Requirements

Execution-phase design must require:

- exact candidate id
- candidate freshness proof
- risk contract hash
- final review packet hash
- accepted Telegram final approval intent
- human confirmation record matching the candidate, risk hash, and packet hash
- exact confirmation phrase:

```text
I CONFIRM ONE TINY LIVE ORDER FOR <candidate_id> WITH RISK <risk_contract_hash> AND PACKET <packet_hash>; MAX LOSS <amount>; I UNDERSTAND THIS CAN LOSE REAL MONEY.
```

The phrase must not be accepted if candidate, hashes, max loss, or readiness state differ from the current gate evidence.

## Protective Order Requirements

Execution-phase design must require:

- protective stop configured before or atomically with the entry plan
- take-profit configured before or atomically with the entry plan
- protective order mode reviewed and safe
- protective readiness true
- no live attempt if protective orders cannot be verified
- immediate abort if protective order creation or verification fails
- post-entry verification of open order and protective state

## Account / Funding Requirements

Execution-phase design must require:

- explicit operator authorization before any account or balance check
- account/funding readiness confirmed without printing secrets
- no private env or credential values in logs or output
- no live order if funding is unknown, insufficient, or ambiguous
- no live order if conflicting BTCUSDT positions or orders are unknown

## Position Size Cap Requirements

Execution-phase design must require:

- one order only
- minimum viable tiny position
- explicit position size cap
- isolated margin where applicable
- no averaging down
- no martingale
- no scale-in after first win
- no second order before postmortem

## Max Loss Cap Requirements

Execution-phase design must require:

- explicit max loss amount in the confirmation phrase
- max loss derived from the approved risk contract
- no live order if max loss is missing, mismatched, or above cap
- immediate abort if stop loss cannot be placed or verified

## Emergency Rollback Requirements

Execution-phase design must require:

- reviewed kill-switch plan
- reviewed emergency cancel plan
- exact manual operator steps for exchange UI verification
- exact safe command surfaces if a future authorized cancel path exists
- no service restart or production action by Codex unless explicitly instructed
- immediate halt after any discrepancy

## Postmortem Requirements

After the first live attempt, the phase must require:

- order id or explicit failed-at step
- timestamp
- candidate id
- entry
- stop
- take profit
- size
- max risk
- fees and slippage when available
- protective order verification result
- alert, ledger, and execution consistency result
- operator behavior review
- result
- lessons
- go/no-go recommendation for any future second order

No second order may be considered until the postmortem is complete.

## Explicit User Authorization Requirement

R107 or any later execution phase may not place orders, call Binance order endpoints, enable live flags, or create executable live payloads unless the user explicitly authorizes that exact action in the current future phase.

## Do Not

- Do not implement execution behavior from this draft.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints unless explicitly authorized.
- Do not enable live flags.
- Do not create live endpoints.
- Do not modify strategy logic.
- Do not modify execution connector behavior.
- Do not expose secrets.
- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart services.

