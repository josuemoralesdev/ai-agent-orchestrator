# R170 Env Role Adapter Preview No Write

## Phase

R170 Env Role Adapter Preview No Write

## Branch

`r170-env-role-adapter-preview-no-write`

## Classification

- Primary: WIRING / INTEGRATION
- Secondary: EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT, DUPLICATE RISK
- Duplicate risk: HIGH

## Purpose

Add a code-level adapter preview for the R169 Binance env role split. The preview should show which role-specific variables would be selected for market data, account-read, and future live roles without writing env files or calling Binance.

## Scope

R170 should:

- prefer role-specific variables when present:
  - `HAMMER_MARKET_BINANCE_API_KEY`
  - `HAMMER_MARKET_BINANCE_API_SECRET`
  - `HAMMER_ACCOUNT_READ_BINANCE_API_KEY`
  - `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET`
  - `HAMMER_LIVE_BINANCE_API_KEY`
  - `HAMMER_LIVE_BINANCE_API_SECRET`
- preserve backward compatibility with `BINANCE_API_KEY` / `BINANCE_API_SECRET`
- report pair-source consistency using only presence, lengths, and hash previews
- keep account-read use behind `BINANCE_CONNECTOR_MODE=read_only`
- keep future live variables disabled unless a later explicit live phase authorizes use

## Non-Negotiables

- Do not write `.env`.
- Do not write `/home/josue/.config/hammer-radar/*.env`.
- Do not mutate config files.
- Do not call Binance.
- Do not call account, balance, order, test-order, protective, transfer, or withdraw endpoints.
- Do not create order payloads.
- Do not enable live trading.
- Do not disable the kill switch.
- Do not print secrets or full API keys.
- Do not commit, merge, or tag.

## Suggested Validation

```bash
.venv/bin/python -m py_compile src/app/hammer_radar/operator/inspect.py
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_env_role_split_proposal.py
git diff -- .env || true
git diff -- configs/hammer_radar/tiny_live_risk_contracts.json || true
git diff -- configs/hammer_radar/lane_controls.json || true
```

R170 remains preview-only. Any env write belongs to a later explicit migration phase.
