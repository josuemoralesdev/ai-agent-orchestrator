# R157 Short Paper Evidence Capture Loop

## Phase

`R157`

## Branch

`r157-short-paper-evidence-capture-loop`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): EXTENSION OF EXISTING CAPABILITY, WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R156 packaged `BTCUSDT|8m|short|ladder_close_50_618` as the next short strategy review door but kept it paper-only. R157 should collect bounded, auditable paper evidence for that exact lane before any future short operator review.

## Main Objective

Collect bounded paper-only evidence for the BTCUSDT 8m short lane, including fresh/stale candidates, paper outcomes, stop frequency, and heartbeat records.

## Required Scope

- Target only `BTCUSDT|8m|short|ladder_close_50_618`.
- Reuse existing watcher, expanded paper watch, fresh signal router, paper execution, and outcome parsers where possible.
- Use a bounded scan or heartbeat loop.
- Track fresh candidates, stale candidates, paper executions, closed paper outcomes, and stop dominance.
- Append local audit/heartbeat records only after exact confirmation if recording is added.

## Safety Constraints

- No lane mode changes.
- No short lane promotion.
- No tiny-live setting.
- No Binance calls.
- No order payloads.
- No protective payloads.
- No signed request material.
- No env mutation.
- No global live flag mutation.
- No kill-switch disable.
- No fake paper proof.

## Expected Validation

Run focused compile and tests for the new R157 module and inspect CLI wiring, then run related R153/R154/R156 tests.

## Expected Output

R157 should produce a paper-only evidence capture summary and a clear next operator move:

- continue paper watch
- record evidence capture
- rerun R156 packet
- wait for more short evidence
