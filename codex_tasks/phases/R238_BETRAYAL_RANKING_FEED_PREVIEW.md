# R238 Betrayal Ranking Feed Preview

## Purpose

Consume R237 betrayal true inverse capture preview rows and prepare a paper-only betrayal ranking/performance feed preview.

## Required Scope

- Read latest `betrayal_true_inverse_outcome_capture_bridge.ndjson`.
- Read R236/R235 context only as needed for source identity and outcome tracking lineage.
- Project which betrayal true-inverse identities can feed ranking after outcomes exist.
- Report ranking/performance schema gaps and promotion blockers.
- Produce preview rows only.

## Non-Negotiable Safety

R238 must not:

- write configs
- mutate env files
- append to or rewrite normal `paper_outcomes.ndjson`
- rewrite historical ledgers
- call Binance or any network
- create executable order payloads
- place orders
- transfer or withdraw
- set any lane `tiny_live`
- write risk contract config
- promote betrayal
- promote signal origins
- promote lanes
- infer tiny-live readiness from betrayal evidence
- infer live readiness
- authorize live execution
- change the official tiny-live lane `BTCUSDT|8m|short|ladder_close_50_618`

## Expected Output

- betrayal ranking feed preview rows
- ranking/performance readiness summary
- promotion evidence readiness projection with promotion blocked
- safety flags proving no config, network, order, promotion, or normal paper-outcome mutation

## Validation Expectations

- Focused tests for preview-only behavior.
- Tests proving promotion and live readiness remain false.
- Tests proving normal paper outcomes are not appended or rewritten.
- Tests proving no Binance/network/order/transfer/withdraw actions occur.
