# R259 Tiny-Live Fresh Cycle Checkpoint

## Purpose

R259 should coordinate the fresh-cycle checkpoint after R258 reports that the
current manual submit path is blocked by stale signed request context or
manual-control review needs.

## Scope

- Still no real submit.
- Still no automatic live-control arming.
- Still no Binance order, test-order, account, private, or signed endpoint
  calls.
- Still no duplicate submit.
- Still no order placement.
- Still no secrets printed or persisted.

## Required Fresh-Cycle Checks

1. Run or verify R253 final readonly mark refresh.
2. Run or verify R253B fresh signed request regeneration.
3. Run or verify R254 submit gate preview.
4. Run or verify R255 dry preview.
5. Verify outputs are fresh enough for a later manual decision.
6. Verify the intended live-control state without mutating controls.
7. Produce the final R260 manual live-submit execution checkpoint.

## Safety Requirements

- `submit_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `network_allowed=false` except for any separately authorized R253 public
  readonly refresh command in its own phase boundary.
- `live_controls_armed_by_phase=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`

## Expected Output

R259 should emit a checkpoint packet that states whether the R253/R253B/R254/R255
fresh cycle is complete and fresh enough, whether live controls still require
manual operator review, and whether a later R260 manual live-submit execution
checkpoint can be prepared. It must never auto-submit.
