# R174 Funding Gate Sync After Role-Specific Account Read

## Phase

R174 Funding Gate Sync After Role-Specific Account Read

## Classification

- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk: MEDIUM

## Purpose

Run only after R173 verifies that `account_read` uses role-specific `HAMMER_ACCOUNT_READ_*` variables. Use the latest explicit read-only balance check result to sync the funding gate context without env writes, live execution, or lane changes.

## Non-Negotiables

- Do not write env files.
- Do not mutate configs or lane modes.
- Do not enable live execution.
- Do not disable the kill switch.
- Do not call order, test-order, protective, transfer, or withdraw endpoints.
- Do not place orders.
- Do not print secrets or full API key/secret values.
- Do not call Binance by default.
- Use only explicit prior read-only balance evidence unless the operator separately authorizes a read-only check.

## Required Inputs

- Latest R173 verification record showing `account_read_role_verification.passed=true`
- Latest explicit read-only balance check result from `logs/hammer_radar_forward/readonly_balance_checks.ndjson`
- Existing funding precheck/sync surfaces

## Expected Output

- A funding evidence sync surface that reports whether funding remains `ACCOUNT_NOT_FUNDED`, `UNKNOWN`, or ready for review based on explicit read-only evidence
- Append-only recording only after an exact R174 confirmation phrase
- Safety object proving no env write, no config write, no live execution, no orders, no trading endpoint calls, no transfer/withdraw, and no secrets shown

## Validation

Run focused tests for the new R174 surface and related R173/R164/R163 funding tests. Run no default network checks unless the operator explicitly authorizes a read-only balance check.
