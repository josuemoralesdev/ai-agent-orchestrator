# R301 Manual Operator Dry-Run Arming Post-Arm Certificate

R301 adds a post-arm certificate over the existing R278/R300 exact-lane dry-run arming path. It observes whether the human operator manually armed the requested exact lane outside Codex, then reports whether dry-run autonomy is ready to wait for a real matching R298/R299 candidate.

R301 does not create a new arming control, scheduler, candidate watcher, final console, or order path.

## Behavior

- Before manual operator arming, the expected status is `MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_NOT_ARMED`.
- After the human operator manually arms `BTCUSDT|44m|long|ladder_close_50_618` outside Codex, the expected status is `MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_CERTIFIED`.
- Invalid, near-miss, paper-only, unknown, or non-live-qualified lanes return `MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_BLOCKED`.
- If live execution flags are detected true, R301 blocks with `live_execution_flag_detected`.
- The operator arms/disarms/tunes risk/kills the system. The machine only waits for and dry-run triggers real matching candidates when armed and all gates are open.

## Safety

R301 is dry-run post-arm certification only:

- no Codex arming or disarming
- no mutation of `configs/hammer_radar/autonomous_arming_state.json`
- no env mutation
- no live config mutation
- no risk contract mutation
- no final live submit command
- no executable payload
- no order payload
- no Binance order endpoint
- no Binance test-order endpoint
- no leverage or margin mutation endpoint
- no fake/test candidate input
- no per-signal operator approval requirement

Even when `global_auto_live_enabled=true` appears in the dry-run arming state, R301 keeps `dry_run_only=true`, `live_execution_enabled=false`, `allow_live_orders=false`, `final_command_available=false`, `submit_allowed=false`, `real_order_forbidden=true`, and `order_placed=false`.

## Interfaces

CLI:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-manual-operator-dry-run-arming-post-arm-certificate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R301 post-arm certificate; no Codex arming; no submit; no order." \
  --record-manual-operator-dry-run-arming-post-arm-certificate
```

API:

```text
GET /tiny-live/manual-operator-dry-run-arming-post-arm-certificate/status
GET /tiny-live/manual-operator-dry-run-arming-post-arm-certificate/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618
```

The API is read-only and never records the R301 ledger.

Print-only plan:

```bash
bash scripts/hammer_print_r301_manual_operator_dry_run_arming_post_arm_certificate_plan.sh
```

## Manual Rollback

R301 packets and the print-only plan include the existing R278 disarm command. The rollback remains manual-operator-only and dry-run-only.

## Next Phase

The expected next phase should continue observing a manually armed dry-run lane through the timer/R298/R299 path and certify real-candidate dry-run behavior without enabling live orders, exposing final submit, or adding a new order path.
