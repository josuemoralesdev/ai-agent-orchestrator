# R173 After Account Read Env Migration Verify

## Phase

R173 After Account Read Env Migration Verify

## Classification

- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk: HIGH

## Purpose

Run after the operator manually sources `HAMMER_ACCOUNT_READ_BINANCE_API_KEY` and `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET` from the R172 packet. Verify the R171 adapter selects the account-read role-specific pair and that funding/read-only checks remain safe.

## Scope

R173 should:

- verify `env-role-adapter-preview` reports `account_read.selected_pair_source=role_specific`
- verify `legacy_fallback_used=false` for account-read
- verify `future_live` remains disabled and does not fall back to legacy
- run `funding-readonly-precheck` without network by default
- run `readonly-balance-check` without network by default
- optionally run `readonly-balance-check --allow-readonly-network-check` only if the operator explicitly approves the read-only network check
- keep env/config/lane files unchanged

## Non-Negotiables

- Do not write `.env`.
- Do not write `/home/josue/.config/hammer-radar/*.env`.
- Do not mutate configs or lane modes.
- Do not print full API keys or secrets.
- Do not call Binance unless the operator explicitly approves the read-only network check.
- Do not call order, test-order, protective, transfer, or withdraw endpoints.
- Do not place orders.
- Do not enable live trading.
- Do not disable the kill switch.
- Do not commit, merge, tag, or push.

## Suggested Commands

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward env-role-adapter-preview
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward funding-readonly-precheck
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readonly-balance-check
```

Optional operator-approved read-only network check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readonly-balance-check --allow-readonly-network-check
```

## Safety Result Required

Report:

- env written: false
- env mutated: false
- config written: false
- order placed: false
- real order placed: false
- execution attempted: false
- Binance order/test/protective endpoints called: false
- transfer called: false
- withdraw called: false
- secrets shown: false
- live execution enabled: false
- kill switch disabled: false
