# R296 Test-Only Matching Candidate Trigger Certificate

R296 certifies the positive autonomous trigger branch with fake, test-only candidate input for an already allowed live-qualified lane. It extends the R294 dry-run lane arming rehearsal and R295 timer-observed armed-lane wait certificate instead of creating a parallel candidate engine, scheduler, or execution path.

## What It Certifies

- Matching lane: an explicitly injected test-only candidate whose lane equals the requested allowed lane records a simulated dry-run lifecycle.
- Nonmatching lane: an explicitly injected test-only candidate whose lane differs from the requested lane records no trigger.
- Near-miss, paper-only, unknown, empty, non-BTCUSDT, wrong timeframe, wrong direction, wrong entry mode, or missing exact contract lanes remain blocked.
- The certificate always reports no live order, no test order, no submit, no executable payload, no final command, no live-enable, and no secrets.

## Test-Only Candidate Input

R296 requires one explicit simulation flag:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-test-only-matching-candidate-trigger-certificate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R296 test-only matching candidate trigger certificate; no submit; no order." \
  --simulate-matching-fresh-candidate-for-tests-only
```

The simulated candidate is labeled:

- `simulated_candidate_source="R296_TEST_ONLY"`
- `simulated_candidate_not_real_market_data=true`
- `test_only=true`

If no simulation flag is passed, the packet blocks with `missing_test_only_simulation_flag`. If both flags are passed, it blocks with `conflicting_test_only_simulation_flags`.

## Simulated Lifecycle

For the matching test-only path, R296 records records only:

- `simulated_open_record.mode="SIMULATED_DRY_RUN_ONLY"`
- `simulated_protective_orders.mode="SIMULATED_DRY_RUN_ONLY"`
- `simulated_close_plan.mode="SIMULATED_DRY_RUN_ONLY"`

These fields are audit records, not order payloads. They explicitly include `order_placed=false`, `executable_payload_created=false`, `submit_allowed=false`, and `final_command_available=false` where applicable.

## Operator And Machine Doctrine

The operator arms, disarms, tunes risk, and uses the kill switch. The machine auto-triggers only when the dry-run lane is armed and all gates are open. R296 does not introduce per-signal operator approval and does not authorize live trading.

## Safety Invariants

R296 preserves:

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
- `secrets_shown=false`

## Visibility

- CLI: `tiny-live-test-only-matching-candidate-trigger-certificate`
- API: `GET /tiny-live/test-only-matching-candidate-trigger-certificate/status`
- Final console: `test_only_matching_candidate_trigger_certificate_panel`
- Print-only plan: `scripts/hammer_print_r296_test_only_matching_candidate_trigger_certificate_plan.sh`
- Optional ledger when explicitly recorded: `logs/hammer_radar_forward/tiny_live_test_only_matching_candidate_trigger_certificate.ndjson`

Plain API status is safe by default. It does not replay the latest recorded certificate,
does not inject a simulated candidate, does not record the R296 ledger, and blocks with
`missing_test_only_simulation_flag`. The explicit query parameter
`simulate_matching_for_tests_only=true` may build a certified in-memory test-only status
packet, but it still does not append the ledger and still reports no final command,
submit permission, executable payload, order payload, live order, or Binance order/test
order call.

## Expected Next Phase

The next phase should use the R296 certificate as evidence that exact-lane test-only candidate matching works under the timer-observed dry-run wait state, then decide whether further operator-visible dry-run lifecycle evidence is needed before any future live-gated work. It must not jump from R296 to live order placement.
