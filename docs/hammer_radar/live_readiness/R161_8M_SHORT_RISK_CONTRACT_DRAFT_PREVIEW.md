# R161 8m Short Risk Contract Draft Preview

Phase: R161

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R161 Follows R160

R160 built a fundless, non-executable dry-run packet for:

```text
BTCUSDT|8m|short|ladder_close_50_618
```

That packet identified a missing target-lane risk contract as one of the blockers before any future tiny-live review. R161 fills only the draft-preview gap. It does not write the risk-contract config, promote the lane, change lane mode, create payloads, call Binance, sign requests, or enable live execution.

## Why The 8m Short Needs A Separate Contract

The existing tiny-live risk-contract config is shaped around current tiny-live long preflight history. The 8m short lane has different review requirements:

- direction is `short`
- golden pocket is resistance/retrace context
- invalidation belongs above relevant swing high or resistance
- take-profit belongs below entry toward downside continuation or liquidity
- the lane remains `paper`
- funding and fresh evidence are still blockers

R161 makes those future contract expectations explicit without making them active.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-risk-contract-draft-preview
```

Record draft preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-risk-contract-draft-preview \
  --record-draft \
  --confirm-short-risk-contract-draft "I CONFIRM SHORT RISK CONTRACT DRAFT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Draft Fields

The target draft uses:

- `mode_target=future_tiny_live_review_only`
- `lane_mode_change_allowed_now=false`
- `current_lane_mode=paper`
- `max_daily_trades=1`
- `max_daily_loss_pct=0.15`
- `max_position_notional_usdt=null`
- `suggested_tiny_live_notional_usdt=null`
- `leverage=null`
- `require_protective_orders=true`
- `require_stop_loss=true`
- `require_take_profit=true`
- `require_short_specific_stop_tp=true`
- `golden_pocket_role=resistance/retrace zone`
- `freshness_seconds=60`
- `cooldown_after_loss_minutes=120`
- `min_fresh_captures_before_review=10`
- `min_paper_outcomes_before_review=30`
- `preferred_win_rate_pct=52`
- `avg_pnl_must_be_positive=true`
- `funding_verified_required=true`
- `operator_approval_required=true`
- `global_kill_switch_required=true`
- `live_flags_required_later=true`
- `config_write_allowed_now=false`
- `execution_allowed_now=false`

## Preview-Only Config Diff

R161 reports a non-executable diff preview:

- whether the target contract would be created later
- whether an existing contract would be modified
- `would_write_config_now=false`
- `preview_only=true`
- the proposed append value for a later reviewed config patch

The preview is a description of a future config patch, not a config mutation.

## Why Config Is Not Written

Config is not written because the target short lane is still blocked by:

- fresh captures below threshold
- funding not verified
- operator approval missing
- lane remains paper
- config write not authorized

Writing the contract would also require a later explicit config-write phase and operator confirmation. R161 only records the draft preview to:

```text
logs/hammer_radar_forward/short_risk_contract_draft_previews.ndjson
```

## Why The Short Lane Remains Paper

The target lane is still:

```text
BTCUSDT|8m|short|ladder_close_50_618 mode=paper
```

R161 does not call the lane-control command interface and does not emit lane-mode apply commands. Existing 13m and 44m long tiny-live modes are not changed.

## No Live Execution

R161 safety output keeps:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `protective_payload_created=false`
- `signed_request_created=false`
- `network_allowed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `protective_order_endpoint_called=false`
- `secrets_shown=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `global_live_flags_changed=false`
- `paper_live_separation_intact=true`

## Next Possible R162

R162 may review whether the R161 draft can be applied later. It should default to blocked unless fresh evidence, funding, operator review, and exact future confirmation are present. R162 must still avoid lane-mode changes, live execution, orders, Binance calls, and any config write unless a future explicit operator confirmation and tests authorize exactly that config-write action.
