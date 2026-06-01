# R166 Readonly Balance Endpoint Fix Or Operator Key Check

## Phase

`R166`

## Branch

`r166-readonly-balance-endpoint-fix-or-operator-key-check`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R165 classifies the R164 read-only balance `HTTPError` into a safer operator-facing cause. R166 should branch from that classification and either fix a proven read-only endpoint mismatch or produce an operator checklist for key permissions, IP restrictions, timestamp/recvWindow, account type, or regional restriction.

## Assigned Agents

- builder: yes
- index: yes
- qa: yes
- security: yes

## Main Objective

Resolve the next safest R165-classified read-only balance blocker without creating any live execution path.

## Capability Scan

Inspect:

- `src/app/hammer_radar/operator/readonly_balance_failure_classifier.py`
- `src/app/hammer_radar/operator/readonly_balance_check.py`
- `src/app/hammer_radar/operator/funding_readonly_precheck.py`
- `src/app/hammer_radar/operator/binance_readonly.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/test_readonly_balance_failure_classifier.py`
- `tests/hammer_radar/test_readonly_balance_check.py`
- `tests/hammer_radar/test_funding_readonly_precheck.py`
- `docs/hammer_radar/live_readiness/R164_READONLY_BALANCE_CHECK_IF_SAFE.md`
- `docs/hammer_radar/live_readiness/R165_READONLY_BALANCE_FAILURE_CLASSIFIER_AND_FUNDING_GATE_RECHECK.md`
- `logs/hammer_radar_forward/readonly_balance_checks.ndjson`
- `logs/hammer_radar_forward/readonly_balance_failure_rechecks.ndjson`

## Reuse / Extend / Create Decision

- Existing capability reused: R164 read-only balance check and R165 failure classifier.
- Existing capability extended: only extend R164/R165 if the classification proves a read-only endpoint or sanitized diagnostic gap.
- New capability created: avoid new modules unless a distinct read-only endpoint adapter boundary is required.
- Why new code is necessary: only if R165 proves the current read-only account-status endpoint or diagnostic detail is insufficient.
- Why this does not duplicate prior work: R166 must consume R165 classification rather than reclassifying failures independently.

## Duplicate Risk Report

- Similar existing modules: `readonly_balance_check.py`, `readonly_balance_failure_classifier.py`, `funding_readonly_precheck.py`, `binance_readonly.py`
- Similar existing endpoints: none expected
- Similar existing CLI commands: `readonly-balance-check`, `readonly-balance-failure-recheck`, `funding-readonly-precheck`
- Similar existing scheduler tasks: none expected
- Similar existing docs: R163, R164, R165 live-readiness docs
- Risk: HIGH
- Mitigation: branch behavior from R165 classification and keep all changes read-only and non-executing.

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call Binance test-order endpoints.
- Do not call protective order endpoints.
- Do not transfer or withdraw.
- Do not create executable order payloads.
- Do not create signed order request material.
- Do not print secrets.
- Do not mutate `.env` files.
- Do not mutate lane config.
- Do not write risk-contract config.
- Do not set any lane to `tiny_live`.
- Do not start or restart services.

## Expected Branches

- If R165 classification is `HTTP_404_OR_ENDPOINT_MISMATCH`, inspect and fix only the read-only endpoint family.
- If R165 classification is `HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION`, produce an operator checklist and keep code changes minimal.
- If R165 classification is `HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE`, produce clock/recvWindow/signature-readonly diagnostics without printing signed material.
- If R165 classification is `ERROR_BODY_NOT_AVAILABLE`, improve sanitized read-only error capture only.
- If R165 classification is temporary/unknown, preserve R165 output and recommend a bounded explicit operator recheck.

## Validation Commands

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/readonly_balance_failure_classifier.py \
  src/app/hammer_radar/operator/readonly_balance_check.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_readonly_balance_failure_classifier.py \
  tests/hammer_radar/test_readonly_balance_check.py \
  tests/hammer_radar/test_funding_readonly_precheck.py
```

## Final Report Format

Report:

- Branch
- R165 classification consumed
- Endpoint/key/checklist decision
- Files changed
- Tests run
- Safety result
- Blockers, if any
