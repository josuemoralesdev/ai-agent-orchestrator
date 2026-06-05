# R209 Readonly Funding Status Recheck

## Classification

- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk: HIGH

## Purpose

Recheck funding status using only the existing role-specific read-only account path and locally recorded read-only balance/funding evidence.

## Non-Negotiables

- No config writes.
- No env writes or mutation.
- No live execution.
- No trading endpoint calls.
- No order, test-order, protective-order, transfer, or withdraw calls.
- No secrets printed.
- No signed trading/order request creation.
- No live flags changed.
- No kill-switch changes.
- No lane mode changes.
- No risk-contract writes.

## Expected Scope

- Reuse existing role-specific account-read selection and funding sync/check surfaces.
- Prefer local ledger inspection by default.
- If a read-only network check is supported, keep it explicitly gated by the existing read-only safety mechanism.
- Report sanitized status only: funded/not funded/unknown, available USDT if already safely available, source ledger, timestamp, and blockers.

## Output

Produce a local readiness/funding report that can feed later tiny-live blocker rechecks without authorizing live execution.
