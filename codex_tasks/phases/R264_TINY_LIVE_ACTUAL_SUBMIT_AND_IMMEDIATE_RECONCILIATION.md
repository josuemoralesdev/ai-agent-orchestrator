# R264 Tiny-Live Actual Submit And Immediate Reconciliation

## Objective

Implement the actual submit checkpoint for:

`BTCUSDT|8m|short|ladder_close_50_618`

R264 is the first phase that may submit real orders, and only after all
pre-submit gates pass.

## Required Preconditions

- Latest R263 final console controls are armed.
- Latest R263 record includes experimental 8m short lane acceptance.
- Latest R262B percentage risk contract fit is valid.
- Latest signed triplet is fresh enough for submit.
- No duplicate live submit exists for the idempotency key.
- Operator supplies the exact R264 submit phrase.
- Kill switch and scoped lane controls allow the tiny-live submit.
- Runtime credentials are available without printing or persisting secrets.

## Submit Scope

If and only if every precondition passes, submit exactly three Binance Futures
orders in this sequence:

1. Main market order.
2. Reduce-only stop order.
3. Reduce-only take-profit order.

No extra orders. No alternate lanes. No automatic retry that creates duplicate
orders.

## Reconciliation

Immediately reconcile and persist:

- exchange order ids for main, stop, and take-profit
- order statuses
- submitted quantities and sides
- reduce-only flags for protective orders
- partial success handling
- abort state if one protective order fails after main order success

## Non-Negotiables

- Require R263 controls armed.
- Require R262B valid contract-fit triplet.
- Require exact submit phrase.
- Require idempotency no-duplicate check.
- Handle partial success explicitly.
- Do not submit more than the three-order triplet.
- Do not submit if R263 lane/fisherman acceptance is missing.
- Do not expose secrets, signatures, auth headers, or environment values.
- Do not mutate risk contracts, strategy promotion, paper outcomes, or
  performance ledgers.

## Expected Outputs

- CLI checkpoint command.
- API endpoint only if explicitly safe and operator-gated.
- Submit attempt ledger.
- Immediate reconciliation ledger.
- Tests for no duplicate submit, exact phrase, partial success, and exact
  three-order sequence.
