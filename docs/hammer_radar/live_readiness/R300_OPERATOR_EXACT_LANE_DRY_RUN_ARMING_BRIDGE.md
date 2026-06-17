# R300 Operator Exact-Lane Dry-Run Arming Bridge

R300 adds an operator-facing bridge over the existing R278 autonomous dry-run arming state, R298 real-candidate dry-run trigger bridge, R299 timer observation certificate, and R292 timer health.

It does not create a new arming system, scheduler, candidate watcher, config, or order path.

## Behavior

- Default expected state is `OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_NOT_ARMED`.
- Codex must not arm or disarm the system from this phase.
- Codex must not mutate `configs/hammer_radar/autonomous_arming_state.json`.
- The operator may manually arm or disarm outside Codex using the printed R278 commands.
- After the operator manually arms the exact requested lane, R300 should certify `OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED`.
- Invalid, near-miss, paper-only, unknown, or non-live-qualified lanes return `OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_BLOCKED`.

## Safety

R300 is dry-run arming visibility only:

- no live execution enable
- no live orders
- no final submit command
- no executable payload
- no order payload
- no Binance order endpoint
- no Binance test-order endpoint
- no leverage or margin mutation endpoint
- no env mutation
- no live config mutation
- no risk contract mutation
- no per-signal operator approval requirement

The packet hard-sets `final_command_available=false`, `submit_allowed=false`, `real_order_forbidden=true`, `order_placed=false`, `binance_order_endpoint_called=false`, `binance_test_order_endpoint_called=false`, `codex_arming_performed=false`, and `codex_config_mutation_performed=false`.

## Interfaces

CLI:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-operator-exact-lane-dry-run-arming-bridge \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R300 operator exact-lane dry-run arming bridge; no Codex arming; no submit; no order." \
  --record-operator-exact-lane-dry-run-arming-bridge
```

API:

```text
GET /tiny-live/operator-exact-lane-dry-run-arming-bridge/status
GET /tiny-live/operator-exact-lane-dry-run-arming-bridge/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618
```

The API is read-only and never records the R300 ledger.

Print-only plan:

```bash
bash scripts/hammer_print_r300_operator_exact_lane_dry_run_arming_bridge_plan.sh
```

## Next Phase

The next phase should observe an operator-manually armed exact lane through the timer and R298/R299 bridge without adding live submit, order placement, or config mutation from Codex.
