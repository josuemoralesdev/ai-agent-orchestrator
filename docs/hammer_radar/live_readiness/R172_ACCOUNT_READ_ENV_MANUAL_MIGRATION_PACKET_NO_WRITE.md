# R172 Account Read Env Manual Migration Packet No Write

R172 adds a no-write operator packet for migrating the account-capable Binance key pair into the R169/R171 account-read role variables.

## Scope

R172 adds:

- `src/app/hammer_radar/operator/account_read_env_migration_packet.py`
- `account-read-env-migration-packet` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/account_read_env_migration_packets.ndjson` as an append-only packet ledger after exact confirmation

The packet fingerprints `/home/josue/.config/hammer-radar/binance-live.env` with hash previews and lengths only. It does not print secrets, write env files, mutate configs, call Binance, sign requests, create order payloads, place orders, enable live flags, or disable the kill switch.

## Manual Account-Read Variables

The operator should create/use these role-specific shell variables manually:

- `HAMMER_ACCOUNT_READ_BINANCE_API_KEY`
- `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET`

Legacy `BINANCE_API_KEY` / `BINANCE_API_SECRET` remain unchanged. R171 still supports legacy fallback, but after manual migration the expected account-read adapter source is `role_specific` with `legacy_fallback_used=false`.

## Manual Source Commands

The packet emits this command shape for the operator to run manually. The commands assign variables without echoing secret values:

```bash
set -a
source /home/josue/.config/hammer-radar/binance-live.env
export HAMMER_ACCOUNT_READ_BINANCE_API_KEY="$BINANCE_API_KEY"
export HAMMER_ACCOUNT_READ_BINANCE_API_SECRET="$BINANCE_API_SECRET"
export BINANCE_CONNECTOR_MODE=read_only
export BINANCE_LIVE_TRADING_ENABLED=false
export HAMMER_BINANCE_LIVE_ENABLED=false
export HAMMER_LIVE_EXECUTION_ENABLED=false
export HAMMER_ALLOW_LIVE_ORDERS=false
export HAMMER_GLOBAL_KILL_SWITCH=true
set +a
```

## Verification Commands

Default no-network checks:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward env-role-adapter-preview
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward funding-readonly-precheck
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readonly-balance-check
```

Optional explicit read-only network check, only if the operator approves:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readonly-balance-check --allow-readonly-network-check
```

Expected after manual migration:

- `account_read_selected_pair_source=role_specific`
- `legacy_fallback_used=false`
- `future_live_still_disabled=true`
- funding remains `ACCOUNT_NOT_FUNDED` unless the account is funded

## Packet Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward account-read-env-migration-packet
```

Record with exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward account-read-env-migration-packet --record-packet --confirm-account-read-env-migration "I CONFIRM ACCOUNT READ ENV MIGRATION PACKET RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
```

## Safety Boundary

R172 safety remains:

- `env_written=false`
- `env_mutated=false`
- `config_written=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `signed_readonly_request_created=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `transfer_endpoint_called=false`
- `withdraw_endpoint_called=false`
- `secrets_shown=false`
- `full_api_key_shown=false`
- `full_api_secret_shown=false`
- `global_live_flags_changed=false`
- `paper_live_separation_intact=true`

## Next Phase

R173 should run only after the operator manually sources `HAMMER_ACCOUNT_READ_*` variables. It should verify role-specific account-read selection, run no-network funding and balance checks, and optionally run the explicit read-only network balance check only with operator approval.
