# R84.1 Tiny Live Risk Contract Config

## Purpose

R84.1 adds a local, non-secret tiny-live risk contract configuration for the current R83/R84 top candidate:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

The goal is to let R84 Live Arming Preflight distinguish between missing risk/funding configuration and a candidate that has a complete local preflight contract but still lacks exact operator approval.

R84.1 is configuration and validation only. It does not create tickets, sign payloads, place orders, call Binance, check account balances, modify env files, or enable live execution.

## Why R84.1 Follows R84

R84 correctly selected the R83-supported 13m long candidate but blocked it because risk and funding fields were unavailable:

```text
risk_contract_status=RISK_CONTRACT_MISSING
funding_status=FUNDING_CONFIG_MISSING
final_preflight_status=BLOCKED_BY_MISSING_RISK_CONTRACT
```

R84.1 supplies the local contract needed for preflight review while preserving the final live gate:

```text
operator_approval_status=MISSING_OPERATOR_APPROVAL
```

## Config Path

The non-secret config is stored at:

```text
configs/hammer_radar/tiny_live_risk_contracts.json
```

The file is safe to commit because it contains no API keys, account balances, signatures, or executable order payloads.

## Risk Contract Fields

The current contract includes:

- `candidate_id`
- `symbol`
- `timeframe`
- `direction`
- `entry_mode`
- `enabled_for_preflight=true`
- `entry_price_source=operator_supplied_or_future_ticket_builder`
- `stop_distance_pct`
- `take_profit_distance_pct`
- `risk_reward_ratio`
- `max_position_notional_usdt`
- `max_margin_usdt`
- `max_loss_usdt`
- `leverage`
- `margin_mode`
- `reduce_only_allowed`
- `protective_stop_required=true`
- `take_profit_required=true`
- `order_type=not_created`

## Conservative Defaults

The initial 13m long contract uses:

```text
stop_distance_pct=0.35
take_profit_distance_pct=0.70
risk_reward_ratio=2.0
max_position_notional_usdt=44.0
max_margin_usdt=44.0
max_loss_usdt=4.44
leverage=1
margin_mode=ISOLATED_REQUIRED
order_type=not_created
```

These values are preflight limits only. They do not arm live execution.

## Funding Config

R84.1 adds local funding metadata:

```text
funding_config_present=true
funding_check_mode=LOCAL_CONFIG_ONLY_NO_NETWORK
account_balance_checked=false
account_balance_source=not_checked_no_network
```

The operator must manually verify available USDT before any later live approval phase. R84.1 intentionally does not call account or balance endpoints.

## Validation Rules

A contract is valid only when:

- `candidate_id` exactly matches the supported candidate
- `symbol`, `timeframe`, `direction`, and `entry_mode` match
- stop and take-profit distance or price are present
- `risk_reward_ratio >= 1.5`
- `max_margin_usdt <= 44.0`
- `max_loss_usdt <= 4.44`
- `max_position_notional_usdt <= 44.0`
- leverage is present and conservative
- `margin_mode=ISOLATED_REQUIRED`
- protective stop and take profit are required
- `order_type=not_created`
- no executable order payload exists

Validation failures keep preflight blocked.

## Expected R84 Preflight Effect

With the default config loaded, R84 should move from missing risk/funding blockers to:

```text
risk_contract_status=RISK_CONTRACT_VALID_FOR_PREFLIGHT
funding_status=FUNDING_CONFIG_PRESENT
funding_check_mode=LOCAL_CONFIG_ONLY_NO_NETWORK
operator_approval_status=MISSING_OPERATOR_APPROVAL
final_preflight_status=BLOCKED_BY_MISSING_OPERATOR_APPROVAL
```

This is the intended conservative result. The candidate is not live-ready.

## No-Order Guarantees

R84.1 preserves:

```text
live_execution_enabled=false
allow_live_orders=false
global_kill_switch=true
order_placed=false
real_order_placed=false
execution_attempted=false
order_payload_created=false
network_allowed=false
secrets_shown=false
```

## Smoke Commands

Risk contract:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract
```

R84 preflight:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-arming-preflight
```

R83 source candidate:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  miro-fish-quality-gate
```

API when the local service is already running:

```text
curl -s http://127.0.0.1:8015/live-arming/risk-contract | jq '
{
  status,
  phase,
  execution_mode,
  candidate_id,
  risk_contract,
  validation,
  funding_config,
  order_placed,
  real_order_placed,
  execution_attempted,
  order_payload_created,
  network_allowed,
  secrets_shown
}'
```

## Next Phase Recommendation

R85 should add Exact Operator Approval + Non-Executable Tiny Live Ticket Builder. It should require exact candidate identity, exact risk contract acknowledgement, and explicit operator approval while still producing no executable order payload unless a later phase authorizes that path.
