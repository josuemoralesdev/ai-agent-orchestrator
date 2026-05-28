# R143 Tiny-Live Lane Unlock Contract

R143 records operator intent to unlock selected tiny-live lanes before a fresh watcher-eligible candidate appears. This prevents the operator from chasing signals while preserving the separation between lane intent, future execution conditions, and actual order placement.

The desired state is `UNLOCKED_WAITING_FOR_CONDITIONS`.

It is not `LIVE_ORDER_READY`, not `ORDER_PLACED`, and not `BINANCE_CALLED`.

## Target Lanes

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

Use `--unlock-all-recommended-lanes` for both lanes, or pass one or more `--lane-key` values.

## Unlock Versus Open

Unlocked means the operator has recorded advance lane intent. The system may later evaluate fresh routed candidates against existing autonomous lane, paper proof, tiny-live authorization, protective policy, risk contract, global gate, kill-switch, and live flag requirements.

Open means a real position exists. R143 cannot open a position and cannot create any exchange-submittable payload.

## Lane Unlock Versus Live Execution

R143 is an append-only contract ledger. It does not clear R126, R130, protective policy, global gates, environment flags, or kill-switch requirements.

Future live execution still requires:

- fresh routed candidate
- paper proof / or configured proof waiver if later approved
- R126 gate clear
- R130 tiny-live authorization clear
- protective policy clear
- risk contract clear
- global gates clear
- kill switch intentionally reviewed
- live execution flags explicitly armed in a future phase

## Confirmation Phrase

Recording requires the exact phrase:

```text
I CONFIRM TINY LIVE LANE UNLOCK CONTRACT ONLY; NO ORDER; NO BINANCE CALL.
```

This authorizes only the lane unlock contract ledger. It does not authorize order placement, Binance calls, signed requests, global live flag mutation, kill switch disablement, env mutation, or bypassing future gates.

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-unlock-contract \
  --unlock-all-recommended-lanes
```

Record unlock contract:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-unlock-contract \
  --unlock-all-recommended-lanes \
  --record-unlock-contract \
  --confirm-unlock-contract "I CONFIRM TINY LIVE LANE UNLOCK CONTRACT ONLY; NO ORDER; NO BINANCE CALL."
```

Status:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-lane-unlock-contract \
  --status-only
```

## Ledger

R143 writes only this append-only ledger when confirmed:

```text
logs/hammer_radar_forward/tiny_live_lane_unlock_contracts.ndjson
```

The record stores the unlock contract id, lanes, operator intent, `UNLOCKED_WAITING_FOR_CONDITIONS`, future conditions, non-authorizations, safety flags, and source surfaces.

## Lane Mode Mutation

R143 does not mutate lane config. If `--apply-lane-mode-if-safe` is requested, R143 returns a blocked lane-mode apply result and points back to the existing R124 `lane-control-command` interface. That keeps lane config mutation in the already-audited lane-only command path.

## Safety Constraints

R143 always reports:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `protective_payload_created=false`
- `signed_request_created=false`
- `network_allowed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `protective_order_endpoint_called=false`
- `secrets_shown=false`
- `env_mutated=false`
- `config_written=false`
- `global_live_flags_changed=false`

## Next Phase

R144 should trace why visible local signals do or do not become watcher-eligible candidates: signal existence, timeframe/direction match, `entry_mode` derivation, candidate creation, router emission, paper eligibility, watcher consumption, and exact rejection reasons.
