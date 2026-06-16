# R298 Real-Candidate Dry-Run Trigger Bridge

R298 bridges the R296/R297 test-only proof into the real fresh-candidate watcher path. It reads the existing fresh trigger watch output and evaluates the current real candidate against one requested approved live-qualified lane.

R298 does not create a new watcher, scheduler, arming system, live gate, or order path.

## Outcomes

- `REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT`: no current real fresh candidate is available for the requested lane, so the system waits.
- `REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED`: a real fresh candidate exists, exactly matches the requested approved lane, is live-qualified, has an exact risk contract, and records a simulated dry-run lifecycle only.
- `REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED`: a real candidate exists but is nonmatching, expired, near-miss, paper-only, incomplete, or the requested lane/risk contract is invalid.

## Real Candidate Only

R298 never uses fake candidate input for certification. The public CLI and API have no simulation flags. Unit tests may pass fixture watcher packets directly into the builder, but the runtime CLI/API reads only the existing fresh trigger watch surface.

`READY_TO_WAIT` is expected when no real candidate exists.

## Safety

R298 is dry-run certification only:

- no live execution enable
- no live order
- no Binance order endpoint
- no Binance test order endpoint
- no leverage or margin mutation endpoint
- no executable order payload
- no final submit command
- no per-signal operator approval requirement
- no secrets shown

The simulated lifecycle records use `mode="REAL_CANDIDATE_SIMULATED_DRY_RUN_ONLY"` and force `order_placed=false`, `executable_payload_created=false`, `submit_allowed=false`, and `final_command_available=false`.

## Interfaces

CLI:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-real-candidate-dry-run-trigger-bridge \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R298 real-candidate dry-run trigger bridge; no fake candidate; no submit; no order." \
  --record-real-candidate-dry-run-trigger-bridge
```

API:

```text
GET /tiny-live/real-candidate-dry-run-trigger-bridge/status
GET /tiny-live/real-candidate-dry-run-trigger-bridge/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618
```

The API is read-only and never records the R298 ledger.

Final console:

```text
real_candidate_dry_run_trigger_bridge_panel
```

Print-only helper:

```bash
bash scripts/hammer_print_r298_real_candidate_dry_run_trigger_bridge_plan.sh
```

## Next Phase

The expected next phase should compare recorded R298 real-candidate bridge evidence against timer-observed wait windows and operator visibility requirements. It must still keep real submit, live execution, and executable order payloads unavailable unless a future explicitly approved live phase defines a separate protected gate.
