# R167 Operator Readonly Balance Retry and Funding Sync

## Phase

`R167`

## Branch

`r167-operator-readonly-balance-retry-and-funding-sync`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R166 improves sanitized read-only error capture and failure classification after R165 reported `ERROR_BODY_NOT_AVAILABLE`. R167 should have the operator manually rerun the explicit R164 read-only network check, classify the new sanitized result through R165, and sync the funding gate decision without live execution or lane/config mutation.

## Assigned Agents

- builder: apply only minimal recheck/sync wiring if needed
- index: confirm R164/R165/R166 reuse and duplicate-risk boundaries
- qa: validate no-network previews and any recorded diagnostic outputs
- security: verify no live execution, no order endpoints, no secrets, and no config/env mutation

## Main Objective

Classify the post-R166 explicit read-only balance retry result and sync funding-gate guidance for `BTCUSDT|8m|short|ladder_close_50_618` without changing live/lane/risk state.

## Capability Scan

Inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `docs/hammer_radar/live_readiness/R164_READONLY_BALANCE_CHECK_IF_SAFE.md`
- `docs/hammer_radar/live_readiness/R165_READONLY_BALANCE_FAILURE_CLASSIFIER_AND_FUNDING_GATE_RECHECK.md`
- `docs/hammer_radar/live_readiness/R166_READONLY_BALANCE_ENDPOINT_FIX_OR_OPERATOR_KEY_CHECK.md`
- `src/app/hammer_radar/operator/readonly_balance_check.py`
- `src/app/hammer_radar/operator/readonly_balance_failure_classifier.py`
- `src/app/hammer_radar/operator/readonly_balance_error_sanitizer.py`
- `src/app/hammer_radar/operator/funding_readonly_precheck.py`
- `tests/hammer_radar/test_readonly_balance_check.py`
- `tests/hammer_radar/test_readonly_balance_failure_classifier.py`
- `tests/hammer_radar/test_readonly_balance_error_sanitizer.py`
- existing `readonly_balance_checks.ndjson` and `readonly_balance_failure_rechecks.ndjson` records

## Reuse / Extend / Create Decision

- Existing capability reused: R164 `readonly-balance-check`, R165 `readonly-balance-failure-recheck`, R166 sanitizer/classification fields
- Existing capability extended: only if the new operator retry proves a missing funding-sync field
- New capability created: avoid unless R164/R165 cannot express the post-R166 state
- Why this does not duplicate prior work: R167 should consume the existing read-only ledgers and commands instead of creating another balance checker

## Duplicate Risk Report

- Similar existing modules: `readonly_balance_check.py`, `readonly_balance_failure_classifier.py`, `funding_readonly_precheck.py`
- Similar existing CLI commands: `readonly-balance-check`, `readonly-balance-failure-recheck`, `funding-readonly-precheck`
- Similar existing ledgers: `readonly_balance_checks.ndjson`, `readonly_balance_failure_rechecks.ndjson`, `funding_readonly_prechecks.ndjson`
- Risk: HIGH
- Mitigation: reuse R164/R165/R166 surfaces; do not create a new ledger or command unless strictly necessary

## Operator Manual Retry

The operator may run this after tests pass and env is loaded:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-check \
  --minimum-balance-usdt 44 \
  --allow-readonly-network-check
```

Then classify without network:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-failure-recheck \
  --latest-balance-checks 50
```

## Safety Constraints

- No live execution
- No lane changes
- No config writes
- No env mutation
- No order endpoints
- No test-order endpoints
- No protective order endpoints
- No transfer or withdraw endpoints
- No executable payloads
- No signed trading or order requests
- No secrets, signatures, signed URLs, auth headers, or raw query strings in output

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/readonly_balance_check.py \
  src/app/hammer_radar/operator/readonly_balance_failure_classifier.py \
  src/app/hammer_radar/operator/readonly_balance_error_sanitizer.py \
  src/app/hammer_radar/operator/inspect.py
```

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_readonly_balance_check.py \
  tests/hammer_radar/test_readonly_balance_failure_classifier.py \
  tests/hammer_radar/test_readonly_balance_error_sanitizer.py
```

## Final Report Format

Report:

- Branch:
- Phase Classification:
- Operator retry result:
- Failure classification:
- Funding gate sync:
- Files changed:
- Tests run:
- Smoke checks run:
- Safety result:
- Blockers:
- Recommended next phase:
