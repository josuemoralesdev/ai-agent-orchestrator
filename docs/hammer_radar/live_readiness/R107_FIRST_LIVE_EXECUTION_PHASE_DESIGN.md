# R107 First-Live Execution Phase Design

Phase: R107

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: HIGH

## Executive Summary

R107 is the formal design package for a future first-live execution phase after R106. It defines the evidence chain, operator controls, risk limits, emergency plan, monitoring requirements, and postmortem requirements that must exist before any later phase can request explicit first-live execution authority.

R107 does not execute, arm, approve, or enable live trading. It creates no endpoint, no executable payload, no Binance order call, no Telegram-to-execution wiring, and no environment flag change.

## R107 Scope

R107 creates:
- This first-live execution phase design document.
- A machine-readable design checklist at `configs/hammer_radar/first_live_execution_design_checklist.json`.
- A future R108 dry authorization gate task at `codex_tasks/phases/R108_FIRST_LIVE_EXECUTION_DRY_AUTHORIZATION_GATE.md`.
- Phase index entries for R107 and planned R108.

The design uses the existing R102-R106 chain as prerequisite evidence. R107 does not create another readiness source of truth.

## What R107 Does Not Do

R107 does not:
- Place orders.
- Enable live trading.
- Call Binance order, account, funding, balance, or position endpoints.
- Modify `.env` files or live execution flags.
- Wire Telegram approval intent to execution.
- Treat Telegram approval as execution authority.
- Create live order endpoints.
- Create execution authority.
- Modify runtime trading modules.
- Start, stop, restart, enable, or disable services.
- Commit, merge, tag, push, deploy, or run `sudo`.

## Preconditions From R106

Any future first-live execution phase is blocked unless R106 reports `FIRST_LIVE_ACTIVATION_READY` for the same current candidate/hash tuple.

Required status chain:
- `final-live-preflight` must be `READY`.
- `tiny-live-armed-dry-run` must be `READY_FOR_DRY_RUN`.
- `one-tiny-live-order-protocol` must be `PROTOCOL_PREREQS_READY`.
- `first-live-activation-gate` must be `FIRST_LIVE_ACTIVATION_READY`.

The statuses must be fresh, internally consistent, and tied to the same:
- candidate id
- risk contract hash
- final review packet hash
- final approval intent
- human approval record set

If R106 reports `FIRST_LIVE_BLOCKED`, any first-live execution phase remains blocked.

## Candidate Requirements

A future execution phase must require exactly one candidate:
- Candidate id must be present and match the R102-R106 evidence chain.
- Candidate must be fresh at the time of final authorization.
- Candidate symbol, timeframe, direction, and entry mode must match the approved risk contract.
- Candidate must not be replaced by an advisory, stale, or review-only signal.
- Duplicate readiness surfaces must not disagree about candidate identity or freshness.

If the candidate changes, the full final preflight, dry-run, protocol, activation gate, approval intent, and human approval chain must be regenerated.

## Risk Contract Requirements

The future phase must require a current risk contract from `configs/hammer_radar/tiny_live_risk_contracts.json` or a later approved risk-contract source.

Required fields:
- candidate id
- symbol
- direction
- timeframe
- entry mode
- max margin
- max position notional
- max loss
- leverage
- margin mode
- protective stop requirement
- take-profit requirement

The approved max loss must be equal to or below the configured cap. Missing, mismatched, stale, or ambiguous risk contract evidence blocks execution.

## Packet Hash Requirements

The final review packet hash must:
- Be present in R102/R106 evidence.
- Match the exact candidate and risk contract hash.
- Match the Telegram final approval intent.
- Match the human approval record.
- Remain unchanged between activation readiness and any future dry authorization gate.

Any hash mismatch, missing packet, stale packet, or regenerated packet without renewed approvals blocks execution.

## Telegram Approval Intent Requirements

Telegram may record intent only. A future execution phase must require:
- An accepted R103 final approval intent.
- Candidate id, risk contract hash, and packet hash matching current R106 evidence.
- No blocked or rejected latest approval intent superseding the accepted tuple.
- A clear audit record that says Telegram approval intent is not execution authority.

Telegram commands must never place orders, arm live trading, or override blockers.

## Human Approval Record Requirements

A future execution phase must require a complete human approval record chain:
- R85 ticket review approval record.
- R86 manual funding and environment checklist record.
- R88 final human review packet approval record.
- R89/R89.1 confirmation status showing required records are present and hash-consistent.
- R106 operator confirmation requirement satisfied only by a future explicitly authorized dry authorization gate.

Records must match the same candidate id, risk contract hash, and packet hash.

## Binance Credentials Requirements

A future execution phase may only inspect credential readiness if explicitly authorized in that future phase. It must:
- Report presence booleans only.
- Never print, persist, infer, synthesize, or expose credential values.
- Keep `.env` contents private.
- Block execution if required credentials are missing, ambiguous, unsafe, or loaded from an unapproved source.
- Confirm credential scope is limited to the intended account and tiny-live action.

R107 performs no credential check and loads no secret values.

## Account/Funding Requirements

A future phase must explicitly authorize any account, balance, funding, open order, or position status check before it occurs.

Before any first-live order can be considered, the operator must confirm:
- Account has available USDT for the approved tiny position and fees.
- Funding state is known and adequate.
- Margin mode is acceptable.
- No account restriction blocks entry or protective orders.
- No balances or account identifiers are printed in public output.

Unknown funding state blocks execution.

## Protective Order Requirements

No naked first-live entry may be allowed.

The future execution phase must require:
- Protective stop configured before or atomically with entry.
- Take-profit configured before or atomically with entry.
- Protective mode reviewed and safe.
- Protective readiness true.
- Protective order quantity and side matching the entry.
- Protective stop and take-profit prices derived from the approved risk contract or final packet.
- Immediate abort if protective order creation or verification fails.
- Post-entry verification of live position, open entry status, protective stop, and take-profit state.

If protective orders cannot be verified, the future phase must halt and enter emergency review.

## Position Size Cap Requirements

The future phase must enforce:
- One order only.
- Minimum viable tiny position.
- Max margin cap from the approved risk contract.
- Max notional cap from the approved risk contract.
- Isolated margin where applicable.
- No averaging down.
- No martingale.
- No scale-in after a win.
- No second order before postmortem and explicit future authorization.

Any size ambiguity blocks execution.

## Max Loss Cap Requirements

The future phase must enforce:
- Explicit max loss in the operator confirmation phrase.
- Max loss derived from the approved risk contract.
- Max loss equal to or below the configured cap.
- Stop loss present and verified.
- Fees and slippage considered in postmortem.

Missing, mismatched, or above-cap max loss blocks execution.

## Kill Switch And Rollback Requirements

The future phase must include:
- Reviewed kill-switch state.
- Reviewed emergency cancel plan.
- Reviewed emergency position close plan, if such a path is explicitly authorized.
- Manual exchange UI verification steps.
- Exact safe command surfaces if a later authorized cancel path exists.
- Immediate halt after discrepancy, unknown state, failed protective verification, or unexpected connector response.

Codex must not start, stop, restart, enable, or disable services unless explicitly instructed in a future turn.

## No Conflicting Position Requirement

Before a first-live order can be considered, the future phase must prove:
- No conflicting BTCUSDT position exists.
- No conflicting BTCUSDT open order exists.
- No pending protective order from a prior attempt can conflict.
- No stale paper/live ledger row is being interpreted as real execution state.

Unknown open position or order state blocks execution.

## Operator Confirmation Phrase Requirement

The future phase must require this exact phrase, with live values:

```text
I CONFIRM ONE TINY LIVE ORDER FOR <candidate_id> WITH RISK <risk_contract_hash> AND PACKET <packet_hash>; MAX LOSS <amount>; I UNDERSTAND THIS CAN LOSE REAL MONEY.
```

The phrase must be rejected if:
- Candidate id differs from R106 evidence.
- Risk contract hash differs from R106 evidence.
- Packet hash differs from R106 evidence.
- Max loss differs from the approved risk contract.
- R106 is not `FIRST_LIVE_ACTIVATION_READY`.
- The phrase is typed before a future explicitly authorized dry authorization gate.

Raw `YES`, vague live commands, and `trade now live` must remain blocked.

## Execution Phase Boundaries

R107 defines the boundaries for a future phase. A later execution phase must be explicitly authorized by the user in that future turn and must still:
- Re-run the R102-R106 status chain.
- Re-check candidate/hash consistency.
- Re-check protective readiness.
- Re-check account/funding readiness only if authorized.
- Keep all audit records append-only.
- Emit safety booleans proving whether any execution was attempted.
- Place at most one tiny order only if every future gate passes.

No future phase may inherit execution authority from this document alone.

## Emergency Stop Plan

The future phase must document exact emergency actions before any live order:
- Halt additional order attempts immediately.
- Verify exchange UI position and open order state.
- Cancel unfilled entry if protective orders are unavailable.
- Verify or place protective stop only under a separately authorized safe path.
- Record failed step, timestamps, and observed state.
- Escalate to manual operator intervention on any uncertain state.
- Do not attempt a second automated action to compensate for an unknown first action.

## Post-Order Monitoring Plan

If a future authorized phase places one tiny live order, monitoring must begin immediately and record:
- Order id or failed-at step.
- Exchange timestamp and local timestamp.
- Entry state.
- Protective stop state.
- Take-profit state.
- Position size and notional.
- Max loss.
- Fees and slippage when available.
- Ledger consistency.
- Telegram/operator notification consistency.
- Any discrepancy or manual intervention.

Monitoring must not create another order.

## Postmortem Requirements

The postmortem must be completed before any second order is considered. It must include:
- Candidate id.
- Risk contract hash.
- Packet hash.
- Order id or explicit failed-at step.
- Entry.
- Stop.
- Take profit.
- Size.
- Max risk.
- Fees and slippage when available.
- Protective order verification result.
- Alert, ledger, and execution consistency result.
- Operator behavior review.
- Result.
- Lessons.
- Go/no-go recommendation for any second order.

## Go/No-Go Criteria For Any Second Order

A second order remains blocked until:
- First-order postmortem is complete.
- No unresolved execution, ledger, alert, protective, or operator discrepancy remains.
- The candidate is not reused from stale evidence.
- A new risk contract/packet/approval chain exists if the market state changed.
- The operator explicitly authorizes a separate future phase.
- The future phase proves paper/live separation and kill-switch behavior remain intact.

One successful first-live order does not create standing live execution authority.

