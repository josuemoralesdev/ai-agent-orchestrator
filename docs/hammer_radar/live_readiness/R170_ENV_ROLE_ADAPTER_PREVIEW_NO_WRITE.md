# R170 Env Role Adapter Preview No Write

R170 adds a code-level preview for the R169 Binance env-role split. It reports which env pair would be selected for each intended role without writing env files, mutating configs, calling Binance, creating signed requests, or enabling live execution.

## Scope

R170 adds:

- `src/app/hammer_radar/operator/env_role_adapter_preview.py`
- `env-role-adapter-preview` in the inspect CLI
- append-only preview ledger `logs/hammer_radar_forward/env_role_adapter_previews.ndjson`

The preview reads process environment values only through an injected/env mapping and emits presence, lengths, and SHA-256 hash previews. Full API keys and API secrets are never rendered.

## Resolution Rules

Market data:

- prefer `HAMMER_MARKET_BINANCE_API_KEY` / `HAMMER_MARKET_BINANCE_API_SECRET`
- fall back to `BINANCE_API_KEY` / `BINANCE_API_SECRET` only when the role-specific pair is absent
- mark fallback as `legacy_ambiguous`

Account read:

- prefer `HAMMER_ACCOUNT_READ_BINANCE_API_KEY` / `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET`
- fall back to `BINANCE_API_KEY` / `BINANCE_API_SECRET` only when the role-specific pair is absent
- mark fallback as `legacy_ambiguous`
- report whether runtime flags are read-only, live-disabled, and kill-switch-on

Future live:

- prefer `HAMMER_LIVE_BINANCE_API_KEY` / `HAMMER_LIVE_BINANCE_API_SECRET`
- never fall back to `BINANCE_API_KEY` / `BINANCE_API_SECRET`
- always report `future_live_disabled=true`

## Commands

Preview, no ledger write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  env-role-adapter-preview
```

Rejected recording attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  env-role-adapter-preview \
  --record-preview \
  --confirm-env-role-adapter-preview "wrong"
```

Record preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  env-role-adapter-preview \
  --record-preview \
  --confirm-env-role-adapter-preview "I CONFIRM ENV ROLE ADAPTER PREVIEW RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
```

## Safety Boundary

R170 does not:

- write `.env` or any env file
- mutate config, lane, risk, or runtime state
- call Binance or any network endpoint
- create signed read-only, trading, or order requests
- call order, test-order, protective, transfer, or withdraw endpoints
- create executable payloads
- enable live trading or disable the kill switch
- print full API keys, API secrets, signatures, signed URLs, or raw env values

## Next Phase

R171 should implement the code-level env role adapter for readonly balance and funding precheck paths. It should prefer `HAMMER_ACCOUNT_READ_*` for account-read checks, preserve legacy fallback warnings, avoid env writes, and keep tests fully offline.
