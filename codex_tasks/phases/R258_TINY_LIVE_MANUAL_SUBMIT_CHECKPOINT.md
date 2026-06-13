# R258 Tiny-Live Manual Submit Checkpoint

## Purpose

R258 is the manual checkpoint phase immediately before any user-run real submit
command for:

`BTCUSDT|8m|short|ladder_close_50_618`

R258 must still not auto-submit. It should verify that all final prerequisites
are fresh and intentional, then present a final yes/no manual command packet for
the operator.

## Non-Negotiables

- Do not auto-submit.
- Do not call Binance automatically.
- Do not call order, test-order, account, private, or signed endpoints from Codex.
- Do not sign or regenerate signed requests automatically.
- Do not mutate env, external env files, configs, lane controls, risk contracts, or live controls.
- Do not disable kill switches.
- Do not place orders.
- Do not print, persist, or infer secrets.

## Required Checkpoint Verifications

- Verify R257 final pre-submit arming drill is recorded and still reports manual decision required.
- Verify signed request regeneration is fresh within seconds.
- Verify live controls were intentionally armed by the operator outside Codex.
- Verify R255 dry preview is green after regeneration and arming.
- Verify exact R255 real-submit command template is present.
- Verify reconciliation, partial-success handling, abort cleanup, and duplicate-submit protection remain present.
- Present final yes/no manual command packet.

## Expected Output

- `operator_should_submit_now=false`
- `auto_submit=false`
- `manual_submit_decision_required=true`
- `signed_request_fresh_within_seconds=true/false`
- `live_controls_intentionally_armed=true/false`
- `r255_dry_preview_green=true/false`
- `final_yes_no_manual_command_packet_present=true`
- `submit_allowed=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `network_allowed=false`
- `secrets_shown=false`

## Safety

R258 is a checkpoint and command-packet phase only. Any real submit remains a
separate human action outside Codex automation.
