# R123 Fresh Signal Router

Phase: R123

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM

## Why R123 Exists

Fast-timeframe Hammer Radar signals can expire before a human can approve each individual setup. R122 moved the operator model from stale signal approval to pre-defined lane intent:

```text
symbol | timeframe | direction | entry_mode
```

R123 wires fresh candidate events into those R122 lanes. The router decides whether each local signal is routed, blocked, expired, or ignored, without adding execution authority.

## Candidate To Lane Mapping

The router normalizes local candidate-like records with:

- `symbol`
- `timeframe`
- `direction`
- `entry_mode`
- `candidate_id` or `signal_id`
- `generated_at`, `timestamp`, `closed_at`, or `detected_at`
- optional `score`, `tier`, and `freshness_status`

If a Hammer Radar signal does not carry `entry_mode`, R123 uses the existing strategy preferred entry mode:

```text
ladder_close_50_618
```

The normalized lane key is evaluated through the R122 lane-control module. R123 does not duplicate live eligibility logic.

## Freshness Behavior

Each configured lane has `freshness_seconds`. A candidate is fresh only when:

```text
now - candidate_timestamp <= freshness_seconds
```

If the lane key matches but the candidate is older than the lane freshness window, the router returns:

```text
EXPIRED_SIGNAL
```

If no lane key matches, the router returns:

```text
NO_MATCHING_LANE
```

## Lane Mode Behavior

- `disabled`: never routes; returns blocked/ignored behavior.
- `paper`: routes as `PAPER_OBSERVE` only.
- `armed_dry_run`: routes as `ARMED_DRY_RUN_OBSERVE` only when R122 lane permission allows it.
- `tiny_live`: remains blocked unless existing global gates are ready; R123 still does not execute.

The tiny-live route action is diagnostic:

```text
TINY_LIVE_BLOCKED_BY_GLOBAL_GATES
```

It is not an order instruction.

## Operator Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward fresh-signal-router-status
```

The command returns compact JSON with candidate counts, routed/blocked/expired compact lists, R122 lane summary, top blockers, and hard safety fields. It intentionally omits large live-eligibility recommendation arrays.

If the local signal source is unavailable, the status is:

```text
ROUTER_NO_CANDIDATE_SOURCE
```

If the source exists but no candidates are present, the status is:

```text
ROUTER_NO_CANDIDATES
```

## Non-Execution Boundary

R123 does not:

- place orders
- create order payloads
- call Binance order endpoints
- enable live execution
- mutate env files
- expose secrets
- bypass R102/R106/global gates
- convert lane intent into execution authority

Router safety fields remain false:

```json
{"order_placed":false,"real_order_placed":false,"execution_attempted":false,"order_payload_created":false,"network_allowed":false,"secrets_shown":false}
```

## Next Phases

- R124 lane command interface: safe operator commands/API/UI for changing lane modes.
- R125 autonomous paper lane execution: paper-only lane execution using routed candidates.
- R126 first tiny-live lane execution: only after explicit authorization and existing global gates are satisfied.
