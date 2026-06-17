# R302 Armed Dry-Run Timer Observation Certificate

R302 observes the manually armed dry-run lane under the running timer/scheduler.
It composes existing R301, R300, R299, R298, R292, R288, R287, and fresh-trigger
watch surfaces. It does not create a new scheduler, arming config, candidate
watcher, or order path.

Default lane:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

## Expected WAIT Certificate

When the exact lane is manually armed, timer health is active, recent scheduler
ticks exist, and no real matching fresh candidate exists, R302 returns:

```text
ARMED_DRY_RUN_TIMER_OBSERVATION_WAIT_CERTIFIED
```

This means the machine observes the armed dry-run lane and remains in WAIT. No
fake or test candidate is used.

## Future Trigger-Ready Certificate

If a real fresh candidate later appears for the exact armed lane, R302 may
return:

```text
ARMED_DRY_RUN_TIMER_OBSERVATION_TRIGGER_READY_CERTIFIED
```

This remains dry-run observation only. It does not expose a final live command,
does not submit, and does not create an executable payload.

## Interfaces

CLI:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-armed-dry-run-timer-observation-certificate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R302 armed dry-run timer observation certificate; no submit; no order." \
  --record-armed-dry-run-timer-observation-certificate
```

API:

```text
GET /tiny-live/armed-dry-run-timer-observation-certificate/status
GET /tiny-live/armed-dry-run-timer-observation-certificate/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618
```

Final console panel:

```text
armed_dry_run_timer_observation_certificate_panel
```

Print-only plan:

```bash
bash scripts/hammer_print_r302_armed_dry_run_timer_observation_certificate_plan.sh
```

## Safety

R302 is read-only by default. The API never records and never mutates config.
The CLI records only the R302 ledger when the explicit record flag is used.

R302 keeps these outcomes false:

- `final_command_available`
- `submit_allowed`
- `executable_payload_created`
- `order_payload_created`
- `order_placed`
- `real_order_placed`
- `execution_attempted`
- `binance_order_endpoint_called`
- `binance_test_order_endpoint_called`
- `live_execution_enabled`
- `allow_live_orders`
- `fake_candidate_used`
- `codex_arming_performed`
- `codex_config_mutation_performed`

The manual operator disarm command remains visible for rollback, but Codex does
not run it.

## Next Phase

The expected next phase should continue observing the armed dry-run timer path
or inspect a real trigger-ready observation if a real matching fresh candidate
appears. Live execution remains unauthorized.
