# R168 Operator Readonly Balance Retry And Funding Sync

## Phase

`R168`

## Branch

`r168-operator-readonly-balance-retry-and-funding-sync`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R167 fixes the read-only Binance Futures account signing path after the R164 explicit check returned `-1022`. R168 lets the operator manually rerun the explicit read-only balance check, classify the sanitized result, and sync the funding gate/readiness view without enabling live execution.

## Assigned Agents

- builder: apply only minimal wiring or documentation needed for the retry/funding sync
- index: confirm reuse of R163-R167 surfaces and update phase index if needed
- qa: run preview/recheck validation and safety assertions
- security: verify no order, trading, transfer, withdraw, env, lane, or risk-contract mutation

## Main Objective

Classify the operator's post-R167 explicit read-only balance-check result and sync funding readiness only if the sanitized evidence shows the account is funded.

## Capability Scan

Inspect:

- `src/app/hammer_radar/operator/readonly_balance_check.py`
- `src/app/hammer_radar/operator/readonly_balance_error_sanitizer.py`
- `src/app/hammer_radar/operator/readonly_balance_failure_classifier.py`
- `src/app/hammer_radar/operator/funding_readonly_precheck.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/test_readonly_balance_check.py`
- `tests/hammer_radar/test_funding_readonly_precheck.py`
- `tests/hammer_radar/test_readonly_balance_failure_classifier.py`
- `docs/hammer_radar/live_readiness/R163_FUNDING_READONLY_PRECHECK_AND_BALANCE_GATE.md`
- `docs/hammer_radar/live_readiness/R164_READONLY_BALANCE_CHECK_IF_SAFE.md`
- `docs/hammer_radar/live_readiness/R167_READONLY_BALANCE_SIGNATURE_PATH_FIX.md`

## Reuse / Extend / Create Decision

- Existing capability reused: R163 funding precheck, R164 readonly balance check, R165 failure classifier, R166 sanitizer, R167 signer diagnostics.
- Existing capability extended: only if a small funding-sync summary is missing.
- New capability created: avoid unless required to compose existing records.
- Why this does not duplicate prior work: R168 should consume existing records and commands rather than introduce another balance checker.

## Tests Required

- Preview readonly-balance-check remains no-network.
- Failure recheck classifies the latest sanitized result.
- Funding sync, if added, reads existing balance/funding evidence only.
- No live execution, order endpoint, test-order endpoint, transfer, withdraw, lane config, risk config, or env mutation flags appear.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/readonly_balance_check.py \
  src/app/hammer_radar/operator/readonly_balance_error_sanitizer.py \
  src/app/hammer_radar/operator/readonly_balance_failure_classifier.py \
  src/app/hammer_radar/operator/funding_readonly_precheck.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_readonly_balance_check.py \
  tests/hammer_radar/test_readonly_balance_error_sanitizer.py \
  tests/hammer_radar/test_readonly_balance_failure_classifier.py \
  tests/hammer_radar/test_funding_readonly_precheck.py
```

## Operator Manual Command

Run only after R167 is merged and reviewed:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-check \
  --minimum-balance-usdt 44 \
  --allow-readonly-network-check
```

## Safety Constraints

- No live execution.
- No order or test-order endpoints.
- No protective order endpoints.
- No transfer or withdraw endpoints.
- No executable order payloads.
- No lane changes.
- No config writes.
- No env writes.
- No secrets, signatures, signed URLs, or raw signed query strings in output.
