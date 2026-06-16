# R295 Timer-Observed Armed-Lane Wait Certificate

R295 adds a dry-run audit certificate proving the installed autonomous scheduler timer has observed the armed-lane wait state across recorded scheduler ticks.

It reuses the existing R294 dry-run lane arming rehearsal, R292 timer health, R288 scheduler ledger, R287 autonomous trigger loop, and R286 fresh trigger watch. It does not create another arming system, scheduler, candidate watcher, or timer-health checker.

## What It Certifies

- The requested lane is one of the approved live-qualified dry-run lanes:
  - `BTCUSDT|44m|long|ladder_close_50_618`
  - `BTCUSDT|44m|short|ladder_close_50_618`
  - `BTCUSDT|55m|long|ladder_close_50_618`
- The timer health surface reports the installed dry-run timer active.
- Recent scheduler tick records exist in `logs/hammer_radar_forward/tiny_live_autonomous_trigger_scheduler.ndjson`.
- The latest scheduler tick reports `AUTONOMOUS_TRIGGER_SCHEDULER_ITERATION_RECORDED`.
- The latest trigger loop reports `AUTONOMOUS_TRIGGER_WAIT`.
- The current candidate state is either no fresh candidate yet, or an exact lane match only.
- Cross-lane borrowing is blocked.

## Dry-Run Only

R295 is an observation and certification layer only. It keeps:

- `live_execution_enabled=false`
- `allow_live_orders=false`
- `global_kill_switch=true`
- `final_command_available=false`
- `submit_allowed=false`
- `real_order_forbidden=true`
- `order_placed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `executable_payload_created=false`
- `per_signal_operator_approval_required=false`

R295 does not call Binance order, test-order, leverage, or margin mutation endpoints. It does not mutate env files, live config, or risk contracts.

## Timer Tick Inspection

The certificate reads the existing scheduler ledger and timer-health packet. It does not wait in real time. If no recent scheduler tick records are present, the certificate blocks with `timer_recent_tick_missing`.

## Exact-Lane Matching

The certificate validates the requested lane through the R294 lane validation path. Near-miss, paper-only, empty, unknown, non-`BTCUSDT`, wrong timeframe, wrong direction, wrong entry mode, and lanes without an exact risk contract are blocked.

If a current fresh candidate exists but does not match the requested lane key exactly, the certificate blocks with `current_candidate_does_not_match_requested_lane`.

## Expected WAIT State

When no matching fresh candidate exists, the certified state remains WAIT:

```text
no_matching_candidate_action=WAIT
```

This matches operator doctrine: the operator arms/disarms/tunes risk/kills the system, and the machine only auto-triggers later when the lane is armed and all gates are open. R295 itself never submits.

## Commands

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-timer-observed-armed-lane-wait-certificate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R295 timer-observed armed-lane wait certificate only; no submit; no order." \
  --record-timer-observed-armed-lane-wait-certificate
```

API:

```text
GET /tiny-live/timer-observed-armed-lane-wait-certificate/status
```

Final console field:

```text
timer_observed_armed_lane_wait_certificate_panel
```

Print-only plan:

```bash
bash scripts/hammer_print_r295_timer_observed_armed_lane_wait_certificate_plan.sh
```

## Next Phase Recommendation

Next phase should keep the same safety contract and decide whether to expose a longer timer-observed wait window summary, such as N consecutive WAIT ticks for the exact armed lane, without creating any submit path or weakening dry-run protections.
