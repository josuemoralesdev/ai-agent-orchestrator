# R84 Live Funding + Final Execution Arming Preflight

## Purpose

R84 adds a read-only live arming preflight contract for the top R83-supported Hammer Radar candidate. It checks whether the candidate is ready for operator live arming review, while keeping live execution disabled and never placing or preparing a live order.

R84 may produce:

```text
READY_FOR_OPERATOR_LIVE_ARMING_REVIEW
```

R84 must not produce or imply:

```text
LIVE_ORDER_APPROVED
LIVE_ORDER_PLACED
EXECUTION_ATTEMPTED
```

## Why R84 Follows R83

R83 identified one supported candidate:

```text
normal|BTCUSDT|13m|long|ladder_close_50_618
```

with `MIRO_FISH_SUPPORTS_CANDIDATE`, score `96`, source `ELIGIBLE_FOR_FUTURE_TINY_LIVE`, and Markov regime `BULL_TREND`.

R83 also exposed the remaining blocker:

```text
risk_fields_unavailable
```

R84 turns that into an explicit preflight contract covering risk, local funding configuration, live env locks, kill switch state, and exact operator approval requirements.

## Risk Contract Requirements

R84 requires a local risk contract before a candidate can become ready for operator live arming review.

Required fields include:

- `symbol`
- `timeframe`
- `direction`
- `entry_mode`
- `entry_price_source`
- `stop_price` or `stop_distance_pct`
- `take_profit_price` or `take_profit_distance_pct`
- `risk_reward_ratio`
- `max_position_notional_usdt`
- `max_margin_usdt`
- `max_loss_usdt`
- `leverage`
- `margin_mode`
- `protective_stop_required=true`
- `take_profit_required=true`

Conservative defaults:

```text
max_margin_usdt=44
max_loss_usdt=4.44
max_position_notional_usdt=44
margin_mode=ISOLATED_REQUIRED
order_type=not_created
```

If stop or take-profit risk fields are missing, R84 returns:

```text
BLOCKED_BY_MISSING_RISK_CONTRACT
```

R84.1 adds the local non-secret config surface at:

```text
configs/hammer_radar/tiny_live_risk_contracts.json
```

For the current 13m long candidate, a valid R84.1 config changes the risk status to:

```text
RISK_CONTRACT_VALID_FOR_PREFLIGHT
```

This is still only preflight evidence. The contract keeps `order_type=not_created` and does not create an executable ticket or payload.

## Funding And Local Config

R84 does not call Binance or account balance endpoints. Funding is local/config-only and reports:

- `FUNDING_CONFIG_PRESENT`
- `FUNDING_CONFIG_MISSING`
- `FUNDING_CHECK_DEFERRED_NO_NETWORK`
- `FUNDING_BLOCKED_BY_LIVE_ENV_LOCKS`

Missing local funding config blocks review readiness with:

```text
BLOCKED_BY_FUNDING_CONFIG
```

R84.1 supplies local-only funding metadata:

```text
funding_config_present=true
funding_check_mode=LOCAL_CONFIG_ONLY_NO_NETWORK
account_balance_checked=false
```

That lets R84 report `FUNDING_CONFIG_PRESENT` without checking Binance balance or using secrets. The operator must still manually confirm available USDT before any later approval phase.

## Kill Switch And Live Env

R84 reports safe non-secret live env toggles:

- `HAMMER_BINANCE_LIVE_ENABLED`
- `HAMMER_LIVE_EXECUTION_ENABLED`
- `HAMMER_ALLOW_LIVE_ORDERS`
- `HAMMER_GLOBAL_KILL_SWITCH`

Expected safe preflight state:

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

R84 treats live execution enabled, allowed live orders, Binance live enabled, or kill switch disabled as unsafe for this phase.

## Operator Approval

R84 defines the approval requirement but does not satisfy it automatically.

It reports:

```text
operator_approval_required=true
exact_candidate_id_required=true
exact_risk_contract_required=true
approval_token_required=true
approval_record_required=true
approval_status=MISSING_OPERATOR_APPROVAL
```

`READY_FOR_OPERATOR_LIVE_ARMING_REVIEW` is still review-only. It does not execute, approve, or build a live ticket.

After R84.1 config is valid, the conservative expected final state is:

```text
final_preflight_status=BLOCKED_BY_MISSING_OPERATOR_APPROVAL
```

The risk and local funding blockers are cleared, but exact operator approval remains unsatisfied.

## Preflight Statuses

- `READY_FOR_OPERATOR_LIVE_ARMING_REVIEW`
- `BLOCKED_BY_MISSING_RISK_CONTRACT`
- `BLOCKED_BY_FUNDING_CONFIG`
- `BLOCKED_BY_POSITION_SIZE`
- `BLOCKED_BY_KILL_SWITCH`
- `BLOCKED_BY_LIVE_ENV_LOCKS`
- `BLOCKED_BY_MISSING_OPERATOR_APPROVAL`
- `BLOCKED_BY_STRATEGY_QUALITY`
- `BLOCKED_BY_REGIME`
- `BLOCKED_BY_DATA_INTEGRITY`
- `BLOCKED_BY_BETRAYAL_PENDING`
- `PREFLIGHT_OPERATOR_REVIEW_ONLY`

## No-Live Guarantees

R84 keeps:

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

R84 does not sign payloads, construct executable order payloads, call Binance, modify env files, restart services, or arm execution.

## Smoke Commands

CLI preflight:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-arming-preflight
```

R84.1 risk contract:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-risk-contract
```

R83 quality context:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  miro-fish-quality-gate
```

R82 regime context:

```text
.venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  markov-regime-gate
```

API when the local service is already running:

```text
curl -s http://127.0.0.1:8015/live-arming/preflight | jq '
{
  status,
  phase,
  execution_mode,
  top_candidate_preflight,
  risk_contract,
  funding_preflight,
  live_env_preflight,
  operator_approval_preflight,
  final_preflight_status,
  blockers,
  live_execution_enabled,
  allow_live_orders,
  global_kill_switch,
  order_placed,
  real_order_placed,
  execution_attempted,
  order_payload_created,
  network_allowed,
  secrets_shown
}'
```

## Next Phase Recommendation

R85 should add Exact Operator Approval + Non-Executable Tiny Live Ticket Builder only after R84.1 risk contract fields are complete. R85 must still be explicit, local, operator-approved, and protective-order aware before any later live execution phase is considered.
