# R124 Lane Command Interface

Phase: R124

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM

## What R124 Adds

R124 adds a safe operator command interface for changing R122 lane-control modes:

- `disabled`
- `paper`
- `armed_dry_run`
- `tiny_live`

The interface lives in `src/app/hammer_radar/operator/lane_command_interface.py` and is exposed through the existing `inspect.py` CLI as `lane-control-command`.

## Why It Is Needed

R122 created lane-control intent and R123 routes fresh local candidates into those lanes. The operator now needs a constrained way to list lanes, preview mode changes, and apply explicit mode changes without editing JSON by hand.

R124 only changes lane intent in `configs/hammer_radar/lane_controls.json`. It does not create execution authority.

## Lane Mode Is Not Execution Authority

Changing a lane mode is not permission to place an order.

R124 does not:

- place orders
- create order payloads
- call Binance order endpoints
- enable global live execution
- mutate `.env` files
- change systemd services
- bypass R102/R106/global gates
- weaken risk limits

R106 and the global gates remain authoritative for any future tiny-live execution path. R123 remains diagnostic and non-executing.

## List Lanes

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command --action list
```

The list output is compact JSON. It includes configured lanes, current modes, risk limits, freshness windows, safety fields, and source surfaces used.

## Preview Mode Changes

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action preview-set-mode \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --mode armed_dry_run
```

Preview is the default behavior. A preview never writes `lane_controls.json` and never writes the audit ledger.

## Apply Confirmed Mode Changes

Actual config writes require both `--apply` and the exact confirmation phrase:

```text
I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE.
```

Example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action set-mode \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --mode armed_dry_run \
  --apply \
  --confirm-lane-change "I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE."
```

Confirmed apply changes only the lane `mode`. Existing risk fields such as `max_daily_trades`, `max_daily_loss_pct`, `freshness_seconds`, `cooldown_after_loss_minutes`, and `require_protective_orders` are preserved.

## Tiny-Live Requests

Tiny-live mode requires an additional explicit flag:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-command \
  --action request-tiny-live-mode \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --mode tiny_live \
  --request-tiny-live
```

This remains preview-only unless `--apply` and the exact confirmation phrase are also present.

Even after a confirmed lane config change to `tiny_live`, R122 lane evaluation still reports blockers unless live eligibility and R106/global gates are ready. Tiny-live lane mode is intent, not execution permission.

## Audit Ledger

Confirmed applies write append-only NDJSON records to:

```text
logs/hammer_radar_forward/lane_control_commands.ndjson
```

Each record includes:

- `event_type: LANE_CONTROL_COMMAND`
- command id and UTC timestamp
- action, lane key, requested/previous/resulting mode
- apply and confirmation booleans
- config write status
- blockers and warnings
- safety fields
- source surfaces used

Rejected and preview-only commands do not mutate config and do not write the ledger.

## API Surface

R124 is CLI-only. `approval_api.py` is a broad operator API with execution-adjacent imports, so R124 avoids adding endpoints in this phase to reduce duplicate-risk and blast radius.

## Safety Constraints

R124 always reports:

```json
{"order_placed":false,"real_order_placed":false,"execution_attempted":false,"order_payload_created":false,"network_allowed":false,"secrets_shown":false,"env_mutated":false,"global_live_flags_changed":false}
```

Unknown lanes are rejected by default. Invalid modes are rejected. Risk-limit changes are not supported in R124.

## Next Phases

- R125 autonomous paper lane execution: route fresh R123 signals into paper execution records while respecting lane modes, max daily trades, and cooldowns.
- R126 first tiny-live lane execution: only after explicit future authorization and existing global gates are satisfied.
