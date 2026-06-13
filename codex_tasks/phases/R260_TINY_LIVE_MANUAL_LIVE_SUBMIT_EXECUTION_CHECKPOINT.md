# R260 Tiny-Live Manual Live-Submit Execution Checkpoint

## Phase

R260 Tiny-Live Manual Live-Submit Execution Checkpoint

## Branch

`r260-tiny-live-manual-live-submit-execution-checkpoint`

## Classification

- Primary: Manual live-submit execution checkpoint
- Secondary: Fresh-cycle verification, duplicate-submit guard, final operator command packet
- Duplicate risk: EXTREME

## Intent

R260 is the manual execution checkpoint after a fresh cycle is complete. It must
not auto-submit. It should verify that the operator has completed the fresh
cycle and that the final manual live-submit command is safe to display for
human review.

## Required Inputs

- Latest R259 fresh cycle checkpoint.
- Fresh R253 final readonly refresh after R258/R259.
- Fresh R253B signed request regeneration after R253.
- Fresh R254 submit gate preview after R253B.
- Fresh R255 dry preview after R254.
- Latest R258 manual checkpoint re-check after the fresh cycle.
- Read-only lane controls.
- Read-only tiny-live risk contract.
- Duplicate-submit/idempotency evidence.

## Non-Negotiables

- Do not auto-submit.
- Do not call Binance.
- Do not call network endpoints.
- Do not call order/test-order/account/private/signed endpoints.
- Do not place orders.
- Do not sign or regenerate signed requests.
- Do not read, print, or persist secrets.
- Do not mutate env, configs, lane controls, risk contracts, scheduler config, or live controls.
- Do not arm live controls.
- Do not disable kill switches.
- Do not append paper outcomes, strategy performance, or promotion status.
- Do not promote alternate lanes.
- Do not change the official lane.
- Do not set `submit_allowed=true`.
- Do not set `network_allowed=true`.

## Required Checks

R260 should verify:

- fresh signed request age is within seconds of the manual decision threshold.
- R255 dry preview is green after the fresh R253B regeneration.
- live controls were intentionally armed by the operator outside Codex.
- kill switch state allows the operator-intended tiny-live path.
- no duplicate live submit exists for the idempotency key.
- exact three-order triplet is still the intended command:
  - main `SELL MARKET 0.007`
  - stop `BUY STOP_MARKET reduceOnly true`
  - take-profit `BUY TAKE_PROFIT_MARKET reduceOnly true`
- final manual command is shown as a template for the operator to run outside
  the Codex task only.

## Output Requirements

The packet should include:

- `go_for_manual_submit_now=false`
- `operator_must_run_live_command_outside_codex=true`
- `submit_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `network_allowed=false`
- `signed_request_age_seconds`
- R255 dry-preview status
- live-control arming status
- duplicate-submit status
- final manual command template
- explicit do-not-run-yet list when any blocker remains

## Future Operator Boundary

The operator may manually run a live command only outside Codex after reviewing
the R260 packet and accepting all exchange-side risk. Codex must not execute the
live command as part of this task.
