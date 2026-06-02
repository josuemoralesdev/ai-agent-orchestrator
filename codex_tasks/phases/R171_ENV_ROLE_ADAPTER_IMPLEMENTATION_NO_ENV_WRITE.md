# R171 Env Role Adapter Implementation No Env Write

## Phase

R171 Env Role Adapter Implementation No Env Write

## Classification

- Primary: WIRING / INTEGRATION
- Secondary: EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT, DUPLICATE RISK
- Duplicate risk: HIGH

## Purpose

Implement code-level env role adapter wiring for readonly balance and funding precheck paths after R170 preview proves the intended selection order.

## Scope

R171 should:

- reuse `src/app/hammer_radar/operator/env_role_adapter_preview.py`
- prefer `HAMMER_ACCOUNT_READ_BINANCE_API_KEY` / `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET` for account-read checks
- preserve fallback to `BINANCE_API_KEY` / `BINANCE_API_SECRET` only when the account-read role-specific pair is absent
- emit warnings when legacy fallback is used
- keep `BINANCE_CONNECTOR_MODE=read_only` required for account-read use
- keep live flags false and kill switch true
- update tests for readonly balance and funding precheck with injected env mappings

## Non-Negotiables

- Do not write `.env`.
- Do not write any env file.
- Do not mutate config files.
- Do not call Binance in tests.
- Do not create order payloads.
- Do not create signed trading/order requests.
- Do not call order, test-order, protective, transfer, or withdraw endpoints.
- Do not enable live trading.
- Do not disable the kill switch.
- Do not print full API keys or API secrets.
- Do not commit, merge, or tag.

## Suggested Validation

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/env_role_adapter_preview.py \
  src/app/hammer_radar/operator/funding_readonly_precheck.py \
  src/app/hammer_radar/operator/readonly_balance_check.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_env_role_adapter_preview.py \
  tests/hammer_radar/test_funding_readonly_precheck.py \
  tests/hammer_radar/test_readonly_balance_check.py
```

R171 must remain implementation wiring only. Env migration and live execution belong to later explicit phases.
