# R160 Fundless Short Dry-Run Packet and Operator Arming Checklist

Phase: R160

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R160 Follows R159

R159 built a fundless readiness rehearsal for:

```text
BTCUSDT|8m|short|ladder_close_50_618
```

That rehearsal confirmed the lane remains `paper`, funding is `UNKNOWN_NOT_CHECKED`, and the dry-run intent remains non-executable. R160 adds the next runway layer: a more explicit packet and arming checklist for a future 8m short tiny-live review discussion.

R160 does not promote the lane, change config, arm live flags, build order payloads, sign requests, call Binance, or place orders.

## What R160 Adds

R160 adds:

- `src/app/hammer_radar/operator/fundless_short_dry_run_packet.py`
- CLI mode `fundless-short-dry-run-packet`
- append-only ledger `logs/hammer_radar_forward/fundless_short_dry_run_packets.ndjson`

The packet reuses:

- R159 fundless short readiness rehearsal
- R158 short evidence recheck
- R156 short strategy packet concepts
- R157 short paper evidence capture records
- read-only `configs/hammer_radar/lane_controls.json`
- read-only local risk-contract config presence

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fundless-short-dry-run-packet \
  --latest-captures 200 \
  --latest-outcomes 10000 \
  --latest-signals 3000
```

Record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  fundless-short-dry-run-packet \
  --latest-captures 200 \
  --latest-outcomes 10000 \
  --latest-signals 3000 \
  --record-packet \
  --confirm-fundless-short-dry-run "I CONFIRM FUNDLESS SHORT DRY RUN PACKET RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
```

## Fundless Dry-Run Packet Purpose

The packet answers what must be true before any future 8m short tiny-live discussion:

- fresh evidence must meet the R157/R158 threshold
- funding must be verified by a future safe read-only process
- a target-lane risk contract must be reviewed
- short-specific stop, take-profit, and protective policy must be reviewed
- operator approval must use an explicit future phrase
- live flags must remain disabled now and can only be intentionally armed in a later authorized phase

## Why No Executable Payload Is Built

R160 emits dry-run fields only:

- `notional_usdt=null`
- `quantity=null`
- `entry_price=null`
- `stop_price=null`
- `take_profit_price=null`
- `would_build_order_payload=false`
- `would_submit_order=false`
- `would_call_binance=false`
- `executable=false`

These fields are a checklist schema, not a Binance request, not a protective-order request, and not signed request material.

## Operator Arming Checklist

The checklist separates:

- conditions that must be true before future live discussion
- conditions currently true, such as the target lane remaining `paper`
- conditions currently blocked, such as funding and operator approval
- commands and actions explicitly forbidden now

Safe commands are limited to R157 capture, R158 recheck, R159 rehearsal, and R160 packet recording. They do not include live commands, lane apply commands, order commands, or signed request commands.

## Funding Verification Plan

Funding remains fundless and unchecked in R160. The packet states that a future safe check may use `binance-readonly-status / balance read-only if available`, but R160 itself requires no network access and takes no funding action.

## Risk Contract Requirements

R160 requires a future target-lane risk contract review for the 8m short lane. The packet reports:

- `must_exist_for_target_lane=true`
- `max_daily_trades=1`
- `max_daily_loss_pct=0.15`
- `requires_protective_orders=true`
- `short_specific_stop_tp_required=true`
- `contract_change_allowed_now=false`

R160 does not write the risk-contract config.

## Protective Policy Requirements

The short protective policy remains review-only:

- golden pocket role: `resistance/retrace zone`
- invalidation: above relevant swing high or resistance
- take-profit: below entry toward downside continuation or liquidity
- `protective_policy_change_allowed_now=false`

No protective order payload is created.

## Live Flag Lockdown

R160 reports:

- `live_execution_enabled=false`
- `global_kill_switch_authoritative=true`
- `short_tiny_live_authorized=false`
- `lane_mode_change_allowed_now=false`

No live execution is enabled. No lane mode changes are made. Existing `tiny_live` long lanes are not changed.

## Next Possible R161

R161 should draft an 8m short tiny-live risk contract preview only. It should not write config by default, change lane mode, enable live execution, call Binance, create order payloads, or bypass the kill switch.
