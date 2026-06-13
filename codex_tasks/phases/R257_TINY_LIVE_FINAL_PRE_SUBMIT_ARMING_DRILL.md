# R257 Tiny-Live Final Pre-Submit Arming Drill

## Objective

Create the final pre-submit arming drill for the official tiny-live lane:

`BTCUSDT|8m|short|ladder_close_50_618`

R257 must still be no-submit. It should verify that the operator has reviewed
R256, that live controls are in the intended state, that regeneration freshness
is acceptable, and that the exact R255 manual submit command is known.

## Non-Negotiables

- Do not run real submit.
- Do not call Binance.
- Do not call order, test-order, account, private, signed, transfer, or withdraw endpoints.
- Do not sign or regenerate signed requests.
- Do not mutate env/config/lane controls/live controls.
- Do not disable kill switches.
- Do not place orders.
- Do not print or persist secrets.
- Do not auto-run the R255 manual submit command.

## Required Checks

- Verify latest R256 operator runbook record exists and was confirmed.
- Verify latest R255 dry preview exists.
- Verify current submit blockers are understood.
- Verify live controls intended state is reviewed by the operator.
- Verify signed request freshness or regeneration requirement.
- Verify exact R255 command and confirmation phrase are present in the manual decision packet.
- Verify duplicate-submit/idempotency review remains clear.
- Verify post-submit reconciliation plan is reviewed.

## Output

Produce a final manual decision packet that states:

- `operator_should_submit_now=false`
- exact next human action
- R255 command template known
- regeneration freshness status
- live controls intended state review status
- reconciliation plan review status
- all safety flags remain false

R257 is the last drill before any separate, explicit manual live-submit
checkpoint. It must never auto-run the real submit.
