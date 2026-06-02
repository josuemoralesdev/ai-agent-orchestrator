# R174 Funding Gate Sync After Role-Specific Account Read

R174 syncs the funding gate from already-recorded local evidence after R173 verifies the account-read env role is `role_specific`.

## Scope

R174 adds:

- `src/app/hammer_radar/operator/funding_gate_role_specific_sync.py`
- `funding-gate-role-specific-sync` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/funding_gate_role_specific_sync.ndjson` as an append-only sync ledger after exact confirmation

The sync reads local ledgers only:

- `account_read_env_migration_verifications.ndjson`
- `readonly_balance_checks.ndjson`
- `short_evidence_recheck_packets.ndjson` for blocker context only
- `short_risk_contract_apply_reviews.ndjson` as a source surface reference only

It does not call Binance by default or through any R174 option.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward funding-gate-role-specific-sync
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward funding-gate-role-specific-sync --record-sync --confirm-funding-role-specific-sync "wrong"
```

Record with exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward funding-gate-role-specific-sync --record-sync --confirm-funding-role-specific-sync "I CONFIRM FUNDING GATE ROLE-SPECIFIC SYNC RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
```

## Expected Current State

For the current BTCUSDT 8m short family:

- `target_family.current_mode=paper`
- `account_read_role_state.selected_pair_source=role_specific`
- `account_read_role_state.legacy_fallback_used=false`
- `account_read_role_state.runtime_safety_passed=true`
- `account_read_role_state.future_live_disabled=true`
- `latest_balance_state.balance_readiness=ACCOUNT_NOT_FUNDED`
- `funding_gate.funding_sync_status=FUNDING_SYNC_ACCOUNT_NOT_FUNDED`
- `funding_gate.safe_to_arm_live=false`

Tiny-live remains blocked by funding, fresh evidence, risk-contract config, lane mode, operator approval, and global live flags.

## Safety Boundary

R174 safety remains:

- `env_written=false`
- `env_mutated=false`
- `config_written=false`
- `risk_contract_config_written=false`
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

R175 should produce a compact BTCUSDT 8m short tiny-live blocker burn-down across funding, fresh captures, risk contract, lane mode, protective policy, operator approval, and live flags. It must remain non-executing and must not write env/config, change lanes, call Binance, or create executable payloads.
