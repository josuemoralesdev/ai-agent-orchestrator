# Phase R165 Funding Gate Recheck And Readiness Sync

## Phase

`R165`

## Branch

`r165-funding-gate-recheck-and-readiness-sync`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R164 creates a safe read-only balance-check surface. R165 should sync that funding result with the existing BTCUSDT 8m short readiness chain before any later tiny-live review can proceed.

## Assigned Agents

- builder: implement scoped sync surface
- index: map duplicate readiness/funding surfaces
- qa: validate no execution and no config mutation
- security: verify no Binance trading calls and no secret exposure

## Main Objective

Combine R164 balance result, R158 fresh evidence, and R162 contract apply review to decide whether funding remains a blocker.

## Capability Scan

Inspect:

- `docs/hammer_radar/live_readiness/R158_SHORT_EVIDENCE_RECHECK_AND_PROMOTION_READINESS_PACKET.md`
- `docs/hammer_radar/live_readiness/R162_8M_SHORT_RISK_CONTRACT_APPLY_REVIEW_IF_READY.md`
- `docs/hammer_radar/live_readiness/R164_READONLY_BALANCE_CHECK_IF_SAFE.md`
- `src/app/hammer_radar/operator/short_evidence_recheck_packet.py`
- `src/app/hammer_radar/operator/short_risk_contract_apply_review.py`
- `src/app/hammer_radar/operator/readonly_balance_check.py`
- `tests/hammer_radar/test_readonly_balance_check.py`
- existing inspect CLI commands and relevant ledgers

## Reuse / Extend / Create Decision

- Existing capability reused: R158 evidence packet, R162 apply review, R164 readonly balance checks
- Existing capability extended: inspect CLI with a sync/recheck command if needed
- New capability created: minimal funding gate recheck composer only if no existing surface already composes these three inputs
- Why this does not duplicate prior work: R165 should not replace R158, R162, or R164; it only summarizes their latest outputs into a funding/readiness decision

## Safety Constraints

- No live execution
- No lane changes
- No config writes
- No risk-contract config writes
- No Binance order, test-order, protective, transfer, or withdraw endpoints
- No executable payloads
- No signed order requests
- No env mutation
- No secret output

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_readonly_balance_check.py
```

Add focused R165 tests when the phase is implemented.

## Final Report Format

Report branch, phase classification, capability scan, reuse decision, duplicate risk, files changed, tests run, smoke checks, safety result, blockers, and exact manual commands if any.
