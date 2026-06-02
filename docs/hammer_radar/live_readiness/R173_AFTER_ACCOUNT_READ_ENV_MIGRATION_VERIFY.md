# R173 After Account-Read Env Migration Verify

R173 verifies the R172 manual account-read env migration outcome without writing env/config files and without calling Binance by default.

## Scope

R173 adds:

- `src/app/hammer_radar/operator/account_read_env_migration_verify.py`
- `account-read-env-migration-verify` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/account_read_env_migration_verifications.ndjson` as an append-only verification ledger after exact confirmation

The verifier reads only process env and local ledgers. It confirms that `account_read` resolves from `HAMMER_ACCOUNT_READ_*`, legacy fallback is not used, runtime flags are forced read-only/live-disabled/kill-switch-on, and `future_live` remains disabled with no legacy fallback.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward account-read-env-migration-verify
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward account-read-env-migration-verify --record-verify --confirm-account-read-env-migration-verify "wrong"
```

Record with exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward account-read-env-migration-verify --record-verify --confirm-account-read-env-migration-verify "I CONFIRM ACCOUNT READ ENV MIGRATION VERIFY RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
```

## Expected Pass Conditions

- `account_read_role_verification.selected_pair_source=role_specific`
- `account_read_role_verification.legacy_fallback_used=false`
- `runtime_safety_verification.passed=true`
- `future_live_isolation.future_live_disabled=true`
- `future_live_isolation.legacy_fallback_used_for_future_live=false`
- `no_write_verification.env_written=false`
- `no_write_verification.config_written=false`

Funding remains local-context only in this phase. If no explicit read-only balance record exists, `latest_funding_status=UNKNOWN`. If the latest explicit read-only balance record says the account is not funded, R173 reports `ACCOUNT_NOT_FUNDED` and recommends R174 funding evidence sync.

## Safety Boundary

R173 safety remains:

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

R174 should run after R173 passes and after the operator has an explicit read-only balance result to sync. It must not write env files, enable live execution, change lanes, or call trading/order/transfer/withdraw endpoints.
