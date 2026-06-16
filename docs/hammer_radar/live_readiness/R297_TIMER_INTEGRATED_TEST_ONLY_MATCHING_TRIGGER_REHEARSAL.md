# R297 Timer-Integrated Test-Only Matching Trigger Rehearsal

R297 adds a bounded manual rehearsal packet for the timer/scheduler path using an explicit test-only matching candidate. It certifies that, when the scheduler-style path is given an explicit test-only matching candidate, the existing R296 matching-candidate certificate observes the simulated dry-run lifecycle while every live/order surface remains disabled.

## What R297 Certifies

- The rehearsal uses the existing R292 timer-health visibility, R295 timer-observed wait certificate, R296 test-only matching candidate certificate, R294 dry-run lane arming rehearsal, autonomous trigger loop, and scheduler-style summary fields.
- Matching simulation can certify only through an explicit test-only flag and exact lane match.
- Nonmatching simulation confirms no trigger when the simulated candidate lane does not match the requested lane.
- The simulated lifecycle stays `SIMULATED_DRY_RUN_ONLY`.
- Final command, submit, executable payload, order payload, Binance order, and Binance test-order surfaces remain unavailable.

## Timer/Scheduler Integration Boundary

R297 is timer/scheduler integrated because the packet reports timer health and bounded scheduler-style iteration summaries. It is not an installed systemd mutation. The installed dry-run timer remains read-only and real-candidate-only.

The normal systemd timer templates are not changed to inject fake candidates:

- `ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.service.template`
- `ops/systemd/hammer-radar/hammer-autonomous-trigger-scheduler-dry-run.timer.template`

R297 simulation requires one explicit manual/API flag:

- `--simulate-matching-fresh-candidate-for-tests-only`
- `--simulate-nonmatching-fresh-candidate-for-tests-only`

The safe default blocks with `missing_test_only_simulation_flag`.

## Matching And Nonmatching Paths

Matching path:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-timer-integrated-test-only-matching-trigger-rehearsal \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R297 timer-integrated test-only matching trigger rehearsal; no submit; no order." \
  --simulate-matching-fresh-candidate-for-tests-only \
  --iterations 1 \
  --record-timer-integrated-test-only-matching-trigger-rehearsal
```

Nonmatching path:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-timer-integrated-test-only-matching-trigger-rehearsal \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R297 timer-integrated test-only nonmatching no-trigger rehearsal; no submit; no order." \
  --simulate-nonmatching-fresh-candidate-for-tests-only \
  --iterations 1
```

## API And Final Console

Safe default API:

```bash
curl -sS http://127.0.0.1:8015/tiny-live/timer-integrated-test-only-matching-trigger-rehearsal/status | jq .
```

Explicit API simulation is read-only and never records the R297 ledger:

```bash
curl -sS "http://127.0.0.1:8015/tiny-live/timer-integrated-test-only-matching-trigger-rehearsal/status?simulate_matching_for_tests_only=true" | jq .
```

The final console includes `timer_integrated_test_only_matching_trigger_rehearsal_panel`, which uses the safe default read model and does not simulate or record.

## Safety Invariants

R297 preserves:

- `live_execution_enabled=false`
- `allow_live_orders=false`
- `global_kill_switch=true`
- `final_command_available=false`
- `submit_allowed=false`
- `real_order_forbidden=true`
- `executable_payload_created=false`
- `order_payload_created=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `secrets_shown=false`
- `installed_systemd_timer_mutated=false`
- `installed_systemd_timer_fake_candidate_injection_enabled=false`
- `normal_scheduler_default_simulation_enabled=false`

## Expected Next Phase

The next phase should keep the installed timer on real candidates only and may add a broader operator evidence packet that compares R297 test-only rehearsal output against actual timer-observed wait windows, still without live submit or order creation.
