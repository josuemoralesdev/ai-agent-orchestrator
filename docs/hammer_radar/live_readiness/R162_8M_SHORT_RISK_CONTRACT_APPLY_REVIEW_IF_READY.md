# R162 8m Short Risk Contract Apply Review If Ready

Phase: R162

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R162 Follows R161

R161 drafted a preview-only risk contract for:

```text
BTCUSDT|8m|short|ladder_close_50_618
```

R161 proved the target contract is missing, the lane remains `paper`, and the draft would not write config now. R162 adds the next review gate: it answers whether that draft is ready for a future config-apply phase, why it is blocked now, and what the later patch would look like.

## Apply Is Reviewed But Not Performed

R162 is apply-review only. It does not mutate:

- `configs/hammer_radar/lane_controls.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- env flags
- global live flags
- any lane mode

The only optional write is an append-only review record to:

```text
logs/hammer_radar_forward/short_risk_contract_apply_reviews.ndjson
```

That review record requires:

```text
I CONFIRM SHORT RISK CONTRACT APPLY REVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL.
```

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-risk-contract-apply-review \
  --latest-captures 200 \
  --latest-drafts 50
```

Record review only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-risk-contract-apply-review \
  --latest-captures 200 \
  --latest-drafts 50 \
  --record-review \
  --confirm-short-risk-contract-apply-review "I CONFIRM SHORT RISK CONTRACT APPLY REVIEW RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Current Blockers

Expected current readiness is blocked because:

- fresh captures are below the 10-capture threshold
- R158 promotion readiness is not ready for operator review
- funding is `UNKNOWN_NOT_CHECKED`
- operator approval is not provided
- config write authorization is not provided
- the target risk contract is still missing
- any future config apply would require a separate confirmation and phase

The target lane remaining `paper` is required and satisfied for this review.

## Future Config Patch Preview

R162 reports a preview-only patch for a future phase:

- `would_write_config_now=false`
- `would_create_target_contract=true` when the target contract is still missing
- `would_modify_existing_contract=false`
- `preview_only=true`
- patch value reuses the R161 target short contract draft

This patch preview is not a mutation and is not execution authority.

## Future Confirmation Requirements

A future config-apply phase must require:

```text
I CONFIRM 8M SHORT RISK CONTRACT CONFIG APPLY ONLY; NO LANE MODE CHANGE; NO ORDER; NO BINANCE CALL.
```

It must also require tests before apply and must preserve no live execution.

## Why No Lane Mode Changes Happen Here

R162 does not call lane-control apply commands and does not emit lane-mode apply commands. Applying a risk contract in a later phase would still not promote the lane, set short tiny-live, enable global live flags, disable the kill switch, or authorize an order.

## No Live Execution

R162 safety output keeps:

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
- `paper_live_separation_intact=true`
- `env_mutated=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `global_live_flags_changed=false`

## Next Possible R163

R163 should add a read-only funding precheck and balance gate. It must remain no-order, no signed trading request, no secrets printed, and no live enable. If balance checks are supported by an existing connector, they should be read-only and clearly separated from execution authority.
