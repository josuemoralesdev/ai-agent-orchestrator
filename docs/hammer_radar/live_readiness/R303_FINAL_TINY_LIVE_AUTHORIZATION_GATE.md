# R303 Final Tiny-Live Authorization Gate

R303 is the final one-shot tiny-live authorization gate for the exact lane:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

It is not order execution. It does not place orders, call Binance order or
test-order endpoints, change leverage/margin, enable live execution, mutate env
files, mutate live config, mutate risk contracts, arm, or disarm.

## Expected WAIT

When no real matching fresh live-qualified candidate exists, R303 returns:

```text
FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE
```

In WAIT, `final_command_available=false`, `submit_allowed=false`,
`real_order_forbidden=true`, `executable_payload_created=false`, and
`order_payload_created=false`. WAIT is healthy when the exact dry-run lane and
timer path are certified but no real candidate exists yet.

## READY Boundary

R303 returns:

```text
FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT
```

only when the exact lane is live-qualified, dry-run armed, R298-R302 are
certified, the real candidate matches the requested lane, the candidate is
fresh and `LIVE_QUALIFIED`, entry/stop/take-profit are present, the exact risk
contract is valid, protective stop/take-profit preview is valid, Binance
readiness and leverage/margin/wallet/position checks pass, and the one-shot
idempotency guard is clean.

READY makes a manual-only final submit packet available. The packet is marked
`MANUAL_OPERATOR_ONLY`, `ONE_SHOT_TINY_LIVE`, `EXACT_LANE_ONLY`, and
`NO_CROSS_LANE_BORROWING`. The human operator must perform the final submit
manually. Codex and the API must not execute it.

## BLOCKED

Any safety blocker returns:

```text
FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
```

Near-miss lanes, paper-only lanes, mismatched candidates, stale timer state,
not-armed state, missing/invalid risk contracts, missing/invalid protective
preview, wallet/readiness conflicts, position conflicts, fake/test candidates,
or prior live submit records block the gate.

## Interfaces

CLI:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-final-authorization-gate \
  --lane-key "BTCUSDT|44m|long|ladder_close_50_618" \
  --operator-id local_operator \
  --reason "R303 final tiny-live authorization gate review; no submit; no order." \
  --record-final-authorization-gate
```

API:

```text
GET /tiny-live/final-authorization-gate/status
GET /tiny-live/final-authorization-gate/status?lane_key=BTCUSDT|44m|long|ladder_close_50_618
```

Final console panel:

```text
final_tiny_live_authorization_gate_panel
```

Print-only plan:

```bash
bash scripts/hammer_print_r303_final_tiny_live_authorization_gate_plan.sh
```

## Safety

The API status endpoint is read-only and non-recording. The CLI records only the
R303 review ledger when `--record-final-authorization-gate` is explicitly used.
R303 has no submit flag, no order flag, no Binance order flag, and no test order
flag.

Manual disarm remains visible as an operator rollback command. Codex does not
run it.
