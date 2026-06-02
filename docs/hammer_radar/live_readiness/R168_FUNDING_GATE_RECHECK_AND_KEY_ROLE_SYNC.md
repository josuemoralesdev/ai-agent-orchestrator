# R168 Funding Gate Recheck And Key Role Sync

R168 records the post-R167 funding truth and documents Binance key-role fingerprints without exposing secrets or changing runtime state.

## Scope

R168 adds:

- `src/app/hammer_radar/operator/funding_gate_key_role_sync.py`
- `funding-gate-key-role-sync` in the inspect CLI
- append-only ledger `logs/hammer_radar_forward/funding_gate_key_role_sync.ndjson`

It consumes the existing R164 ledger:

```bash
logs/hammer_radar_forward/readonly_balance_checks.ndjson
```

The expected current funding result is:

- `funding_status=ACCOUNT_NOT_FUNDED`
- `balance_readiness=ACCOUNT_NOT_FUNDED`
- `available_balance_usdt=0.0` when present in the latest balance record
- `wallet_balance_usdt=0.0` when present in the latest balance record

## Key Role Fingerprints

R168 reads only enough local env-file content to build safe fingerprints:

- repo `.env`
- `/home/josue/.config/hammer-radar/binance-readonly.env`
- `/home/josue/.config/hammer-radar/binance-live.env`

The output contains only:

- key/secret presence
- key/secret value lengths
- short SHA256 hash previews
- mismatch evidence derived from hash previews and lengths

It never prints full API keys, API secrets, signatures, signed URLs, or raw env values.

## Command

Preview, no ledger write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  funding-gate-key-role-sync
```

Rejected write attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  funding-gate-key-role-sync \
  --record-sync \
  --confirm-funding-key-role-sync "wrong"
```

Record sync only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  funding-gate-key-role-sync \
  --record-sync \
  --confirm-funding-key-role-sync "I CONFIRM FUNDING GATE KEY ROLE SYNC RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE TRADING CALL."
```

## Operator Guidance

Use the account-capable key only for read-only Futures account-balance checks, and force:

- `BINANCE_CONNECTOR_MODE=read_only`
- `BINANCE_LIVE_TRADING_ENABLED=false`
- `HAMMER_LIVE_EXECUTION_ENABLED=false`
- `HAMMER_ALLOW_LIVE_ORDERS=false`
- `HAMMER_GLOBAL_KILL_SWITCH=true`

Do not edit env files automatically. Do not mix the market/read-only key with the account-read secret.

## Safety Boundary

R168 does not:

- call Binance
- place orders
- create executable order payloads
- call order, test-order, protective, transfer, or withdraw endpoints
- mutate `.env`
- mutate env role files
- mutate config files
- change lane modes
- set the 8m short lane to `tiny_live`
- write risk-contract config
- enable live trading
- disable the kill switch

`ACCOUNT_NOT_FUNDED` keeps the funding gate blocked. Live execution remains disabled and no future phase should treat key-role visibility as live authorization.

## Next Phase

R169 should propose clean env role naming for market data, account-read, and future live-trading/account keys without writing env files by default.
