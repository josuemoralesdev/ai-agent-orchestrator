# R133 Lane Control Cockpit UI

R133 adds **Hammer Control Tower**, a read-only FastAPI cockpit for the autonomous lane architecture. It composes R122-R132 lane, router, scheduler, paper proof, tiny-live gate, authorization, kill-switch rehearsal, and live adapter boundary review status into one compact operator view.

This is a visibility layer only. It does not place orders, create Binance payloads, sign requests, mutate env files, write lane config, enable live flags, or bypass R106/global gates.

## Why Lane-Based

R108/R109 centered the operator around manual first-live approval intent for individual candidates. The autonomous architecture now needs the operator to reason about durable lanes:

- which lanes exist
- which lanes are paper, armed dry run, or tiny_live
- whether a fresh signal routed into a lane
- whether scheduler and paper proof are present
- whether the tiny-live lane gate is blocked or near-ready
- whether R132 boundary review is visible before any future R134 dry authorization packet

R133 is therefore lane-based, not signal-approval based.

## Design Choice

The UI follows Option D: Thread Launcher-style Control Tower plus MasonShift sacred gate accents.

- dark graphite background
- compact operational layout
- large lane cards
- green, amber, red, and purple accents
- one red sacred-eye visual for the final tiny-live gate
- copyable safe command snippets
- no action buttons that mutate state

## Routes

- `GET /operator/lane-cockpit`
  - Returns the Hammer Control Tower HTML.
  - Read-only.

- `GET /operator/lane-cockpit/state`
  - Returns compact JSON for the cockpit.
  - Read-only.

There are no R133 POST routes.

## CLI

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-cockpit-state
```

## State Endpoint

The state includes:

- `read_only=true`
- `no_order_buttons=true`
- `global_safety`
- `lanes`
- `selected_lane`
- router, scheduler, paper executor, tiny-live gate, authorization, kill-switch, and adapter boundary summaries
- `next_action`
- `command_pack`
- safety flags proving no order, payload, signed request, network allowance, env mutation, config write, or live flag change occurred

If any source fails, the cockpit returns `LANE_COCKPIT_DEGRADED` while keeping the same safety envelope.

## Command Copy Behavior

The command pack includes status/preview commands only:

- `lane-control-status`
- `fresh-signal-router-status`
- `lane-autonomy-scheduler`
- `autonomous-paper-lane-executor-integration`
- `first-tiny-live-lane-execution-gate`
- `first-tiny-live-autonomous-lane-authorization`
- `live-lane-kill-switch-rehearsal`
- `live-adapter-boundary-final-review`

The command pack does not include confirmation phrases, write flags, Binance endpoints, order payload previews, env mutation, lane config writes, or live execution commands.

## Local Run

If the approval API is already running locally:

```bash
curl -s http://127.0.0.1:8015/operator/lane-cockpit/state | jq '.status, .read_only, .no_order_buttons, .global_safety, .next_action, .safety'
```

R133 does not require starting or restarting services. If the API is not running, use the CLI smoke command above.

## R134 Preparation

R133 prepares R134 by making cockpit, boundary, gate, paper proof, and authorization state visible before any first tiny-live order payload dry authorization packet is considered. R134 must remain non-executing, current-turn explicit, and bound by R132 requirements.
