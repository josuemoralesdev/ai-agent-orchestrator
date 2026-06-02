# R172 Account Read Env Manual Migration Packet No Write

## Phase

R172 Account Read Env Manual Migration Packet No Write

## Classification

- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk: HIGH

## Purpose

Produce exact manual operator instructions for migrating the account-capable Binance key pair into the R169/R171 account-read role variables:

- `HAMMER_ACCOUNT_READ_BINANCE_API_KEY`
- `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET`

Codex must not write env files. The output is a manual migration packet only.

## Non-Negotiables

- Do not write `.env`.
- Do not write `/home/josue/.config/hammer-radar/*.env`.
- Do not mutate configs or lane modes.
- Do not print full API keys or secrets.
- Do not call Binance.
- Do not run readonly balance network checks.
- Do not place orders.
- Do not call order, test-order, protective, transfer, or withdraw endpoints.
- Do not enable live trading.
- Do not disable the kill switch.
- Do not commit, merge, tag, or push.

## Required Scan

Inspect:

- `docs/hammer_radar/live_readiness/R168_FUNDING_GATE_RECHECK_AND_KEY_ROLE_SYNC.md`
- `docs/hammer_radar/live_readiness/R169_ENV_ROLE_SPLIT_PROPOSAL_NO_WRITE.md`
- `docs/hammer_radar/live_readiness/R170_ENV_ROLE_ADAPTER_PREVIEW_NO_WRITE.md`
- `docs/hammer_radar/live_readiness/R171_ENV_ROLE_ADAPTER_IMPLEMENTATION_NO_ENV_WRITE.md`
- `src/app/hammer_radar/operator/env_role_adapter.py`
- `src/app/hammer_radar/operator/env_role_adapter_preview.py`
- `src/app/hammer_radar/operator/funding_gate_key_role_sync.py`
- `src/app/hammer_radar/operator/readonly_balance_check.py`
- `src/app/hammer_radar/operator/funding_readonly_precheck.py`
- `tests/hammer_radar/test_env_role_adapter.py`
- `tests/hammer_radar/test_readonly_balance_check.py`
- `tests/hammer_radar/test_funding_readonly_precheck.py`

## Required Output

Create:

- `docs/hammer_radar/live_readiness/R172_ACCOUNT_READ_ENV_MANUAL_MIGRATION_PACKET_NO_WRITE.md`

The packet must include:

- current role intent summary
- exact manual variables to create
- exact safe operator command examples that do not expose secret values
- verification commands using `env-role-adapter-preview`, `funding-readonly-precheck`, and default no-network `readonly-balance-check`
- expected post-migration adapter output shape
- explicit rollback-by-unset/manual-removal instructions
- safety section proving no env write by Codex, no Binance calls, no orders, no live enable

## Validation

Run:

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/env_role_adapter.py \
  src/app/hammer_radar/operator/env_role_adapter_preview.py \
  src/app/hammer_radar/operator/readonly_balance_check.py \
  src/app/hammer_radar/operator/funding_readonly_precheck.py \
  src/app/hammer_radar/operator/inspect.py
```

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_env_role_adapter.py \
  tests/hammer_radar/test_env_role_adapter_preview.py \
  tests/hammer_radar/test_readonly_balance_check.py \
  tests/hammer_radar/test_funding_readonly_precheck.py
```

## Safety Result Required

Report:

- env written: false
- env mutated: false
- config written: false
- order placed: false
- real order placed: false
- execution attempted: false
- Binance called: false
- transfer called: false
- withdraw called: false
- secrets shown: false
- live execution enabled: false
- kill switch disabled: false
