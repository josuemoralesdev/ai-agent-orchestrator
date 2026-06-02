# R171 Env Role Adapter Implementation No Env Write

R171 implements the R170 no-write env role resolution rules as a shared adapter and wires the account-read role into read-only funding surfaces.

## Scope

R171 adds:

- `src/app/hammer_radar/operator/env_role_adapter.py`
- account-read role resolution in `readonly-balance-check`
- account-read role resolution in `funding-readonly-precheck`
- focused offline tests for role preference, legacy fallback, runtime safety, no secret rendering, and no network/default execution

The phase does not write `.env` files, role env files, or configs. It does not call Binance by default, place orders, create executable payloads, enable live flags, or change lane modes.

## Resolution Rules

Account read:

- prefer `HAMMER_ACCOUNT_READ_BINANCE_API_KEY` / `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET`
- fall back to `BINANCE_API_KEY` / `BINANCE_API_SECRET` only when the account-read pair is absent
- mark fallback with `selected_pair_source=legacy_fallback`, `legacy_fallback_used=true`, and the warning `account_read uses legacy fallback; role-specific HAMMER_ACCOUNT_READ_* variables are preferred.`
- require read-only runtime safety for account-read summaries: `BINANCE_CONNECTOR_MODE=read_only`, live flags false, and `HAMMER_GLOBAL_KILL_SWITCH=true`

Market data:

- prefer `HAMMER_MARKET_BINANCE_API_KEY` / `HAMMER_MARKET_BINANCE_API_SECRET`
- fall back to legacy only when the market role-specific pair is absent
- mark legacy fallback as ambiguous

Future live:

- prefer `HAMMER_LIVE_BINANCE_API_KEY` / `HAMMER_LIVE_BINANCE_API_SECRET`
- never fall back to legacy `BINANCE_*`
- remains disabled pending a separate explicitly approved future live phase

## Output

`readonly-balance-check` now includes sanitized `env_role_resolution`:

```json
{
  "role": "account_read",
  "selected_pair_source": "role_specific|legacy_fallback|missing",
  "api_key_present": true,
  "api_secret_present": true,
  "api_key_hash_preview": "...",
  "api_secret_hash_preview": "...",
  "legacy_fallback_used": false,
  "role_specific_pair_present": true,
  "runtime_safety_ok": true,
  "secrets_shown": false
}
```

`funding-readonly-precheck` also exposes the same account-read resolution under `env_role_resolution`, `local_env_readiness.env_role_resolution`, and `readonly_connector.env_role_resolution`.

## Safety Boundary

R171 safety remains:

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

The existing readonly network path is still gated by `--allow-readonly-network-check`; tests and default smoke checks do not call Binance.

## Next Phase

R172 should produce a manual no-write migration packet for creating `HAMMER_ACCOUNT_READ_*` variables from the account-capable pair. Codex must not write env files, call Binance, or enable live execution in R172.
