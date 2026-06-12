# R256 Tiny-Live Operator Real Submit Runbook And Reconciliation

## Objective

Create the operator runbook for the first manual R255 tiny-live real submit
after R255 dry implementation has been reviewed and validated.

R256 is a runbook and reconciliation phase. It must not auto-run the real
submit command.

## Required Inputs

- Latest R255 dry preview ledger record.
- Latest R254 submit gate preview.
- Latest R253B fresh signed request artifact.
- Current kill switch, lane controls, and live execution state.
- Current tiny-live risk contract.
- Operator-reviewed credential source readiness.

## Required Content

- Final manual pre-submit checklist.
- Exact R255 real submit command for the operator to copy into a terminal.
- Explicit statement that the command is not auto-run by Codex.
- Duplicate protection review and idempotency key inspection.
- Signed request freshness check and regeneration instruction if stale.
- Post-submit exchange reconciliation checklist.
- Required exchange order IDs and statuses to record.
- Verification that stop and take-profit orders are reduce-only.
- Abort paths if one, two, or three orders are rejected.
- Immediate cleanup and kill-switch instructions.
- What to do if only the main order is accepted.
- What to do if main is rejected but one or both exit orders are accepted.
- What to do if stop or take-profit protection is missing after main acceptance.

## Safety

- Do not place orders during runbook creation.
- Do not call Binance from Codex.
- Do not print or persist secrets.
- Do not mutate env/config/lane controls unless a later explicit phase authorizes it.
- Do not disable kill switches from Codex.
- Do not run the R255 real submit phrase during Codex implementation.

## Validation

R256 should verify that the R255 dry preview ledger exists and that R255 still
reports:

- `actual_submit_executed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`

Any real submit remains a manual operator action after review.
