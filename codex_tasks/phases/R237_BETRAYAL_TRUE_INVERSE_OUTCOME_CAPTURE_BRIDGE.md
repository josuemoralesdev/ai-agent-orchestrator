# R237 Betrayal True Inverse Outcome Capture Bridge

## Purpose

Capture or bridge true inverse outcomes for betrayal-tagged paper outcome tracking identities produced by R236, so betrayal evidence can later feed ranking and promotion review through the normal paper-only machinery.

## Required Scope

- Read latest R236 `betrayal_paper_outcome_tracking_bridge.ndjson`.
- Read latest R235 `betrayal_signal_origin_integration_contract.ndjson`.
- Read local betrayal true-paper, betrayal paper signal, shadow outcome, paper outcome, and generic outcome ledgers as read-only context.
- Identify betrayal paper outcome tracking identities that need true inverse/paper outcome evidence.
- Build preview-only outcome capture/bridge rows.
- Report identity gaps, source evidence gaps, window gaps, and rows ready for future paper outcome evidence adoption.
- Optionally append only an R237 audit/preview ledger after an exact confirmation phrase.

## Non-Negotiable Safety

R237 must not:

- write configs
- mutate env files
- write lane controls
- write risk contracts
- set any lane `tiny_live`
- promote betrayal
- promote signal origins
- promote lanes
- infer live readiness
- infer funding readiness
- call Binance
- call any network
- create executable order payloads
- place orders
- transfer or withdraw
- rewrite historical ledgers
- rewrite or backfill `paper_outcomes.ndjson`
- authorize live execution
- disable the kill switch
- change the official tiny-live lane `BTCUSDT|8m|short|ladder_close_50_618`

## Expected Safety State

- `paper_only=true`
- `live_authorized=false`
- `promotion_allowed=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
- `paper_outcome_ledger_rewritten=false`
- `paper_outcomes_appended=false` unless a future phase explicitly creates a separate confirmed paper outcome adoption workflow
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `network_allowed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `signal_origin_promoted=false`
- `lane_promoted=false`
- `betrayal_promoted=false`
- `betrayal_live_authorized=false`

## Validation Expectations

- Focused tests for preview-only behavior.
- Wrong confirmation rejects any ledger recording.
- Correct confirmation appends only the R237 audit ledger.
- `paper_outcomes.ndjson` is not rewritten or appended.
- No config/env mutation.
- No Binance/network/order/transfer/withdraw calls.
- Official tiny-live lane remains unchanged.
