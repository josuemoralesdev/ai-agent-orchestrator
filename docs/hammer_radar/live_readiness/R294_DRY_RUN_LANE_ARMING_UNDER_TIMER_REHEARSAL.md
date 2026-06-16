# R294 Dry-Run Lane Arming Under Timer Rehearsal

## Purpose

R294 adds an operator-visible rehearsal layer for one exact dry-run lane under the running autonomous trigger timer. It proves that the operator can select one approved live-qualified lane for dry-run rehearsal, the timer health can be inspected, and a matching fresh candidate can produce only a simulated dry-run lifecycle.

This is not live execution. It does not submit, sign, create executable payloads, call Binance order/test-order/leverage/margin endpoints, mutate env files, mutate live config, mutate risk contracts, disable the kill switch, or expose a final live command.

## Allowed Lanes

Only these R294 dry-run lane keys are accepted:

- `BTCUSDT|44m|long|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|55m|long|ladder_close_50_618`

The rehearsal is exact-lane only. There is no cross-lane borrowing.

## Blocked Lane Categories

R294 rejects:

- near-miss lanes
- paper-only lanes
- unknown lanes
- empty lane keys
- non-`BTCUSDT` lanes
- lanes outside the three approved R294 keys
- any attempted live/executable/submit path

## Operator Doctrine

The operator arms, disarms, tunes risk, and uses the kill switch. The machine auto-triggers only when the selected dry-run lane is armed and all gates are open. R294 does not introduce per-signal operator approval.

## Timer Interaction

The R294 packet includes:

- timer health status
- timer active state
- recent scheduler tick visibility
- current fresh candidate lane
- exact match between current candidate and requested armed lane

If no fresh matching live-qualified candidate exists, R294 remains `DRY_RUN_LANE_ARMING_REHEARSAL_READY_TO_WAIT` when timer and lane checks are green. If a simulated matching candidate is supplied by the tests-only flag, R294 records only a simulated open/protective/close lifecycle inside its rehearsal packet.

## Why No Live Order Can Occur

R294 hard-sets:

- `dry_run_only=true`
- `live_execution_enabled=false`
- `allow_live_orders=false`
- `global_kill_switch=true`
- `final_command_available=false`
- `submit_allowed=false`
- `real_order_forbidden=true`
- `executable_payload_created=false`
- `order_payload_created=false`
- `order_placed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `per_signal_operator_approval_required=false`

The POST endpoint and CLI record path append only `tiny_live_dry_run_lane_arming_rehearsal.ndjson`.

## Verification Commands

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar \
  -k "dry_run_lane_arming_rehearsal or timer_health or autonomous_trigger_scheduler or final_console or approval_api"

bash scripts/hammer_print_r294_dry_run_lane_arming_rehearsal_plan.sh | sed -n '1,260p'

PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-dry-run-lane-arming-rehearsal \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R294 dry-run lane arming rehearsal only; no submit; no order." \
  --record-dry-run-lane-arming-rehearsal
```

API status:

```bash
curl -sS http://127.0.0.1:8015/tiny-live/dry-run-lane-arming-rehearsal/status | jq .
```

## Rollback And Cleanup

R294 does not mutate env, live config, risk contracts, or systemd. The only record written by R294 is:

```text
logs/hammer_radar_forward/tiny_live_dry_run_lane_arming_rehearsal.ndjson
```

If the operator wants autonomous dry-run arming back to OFF, use the existing helper:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-autonomous-dry-run-disarm-lane \
  --operator-id local_operator \
  --reason "R294 cleanup; return autonomous dry-run arming to OFF." \
  --confirm-dry-run-autonomous-disarm "I CONFIRM AUTONOMOUS DRY-RUN DISARM; RETURN TO OFF."
```

## Next Phase Recommendation

R295 should use real timer-observed state only to compare current armed lane, current fresh candidate, and recent scheduler ticks. It should remain dry-run only unless a later separately approved live phase explicitly changes the safety envelope.
