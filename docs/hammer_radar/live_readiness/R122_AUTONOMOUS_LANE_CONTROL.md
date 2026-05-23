# R122 Autonomous Lane Control Scaffold

Phase: R122

Status: IMPLEMENTED

Classification:
- Primary: NEW CAPABILITY
- Secondary: WIRING / INTEGRATION
- Duplicate risk level: MEDIUM

## Why R122 Exists

Manual approval of individual 4m, 8m, and 13m signals is structurally too slow. By the time an operator sees a candidate, checks readiness, and approves a single stale signal, the setup can already be invalid.

R122 changes the operator model from approving stale individual signals to arming a lane ahead of time. A lane is:

```text
symbol | timeframe | direction | entry_mode
```

Example:

```text
BTCUSDT | 13m | long | ladder_close_50_618
```

The system can then wait for a fresh matching candidate under risk controls in later phases.

## Lane Arming Model

Lane mode expresses intent only:

- `disabled`: no lane intent.
- `paper`: lane can be observed or routed to later paper-only handling.
- `armed_dry_run`: lane may be evaluated for future dry-run readiness but still cannot trade.
- `tiny_live`: reserved for a later explicit execution phase and still blocked by global gates.

The initial R122 config arms only the requested BTCUSDT long ladder lanes:

- `13m`: `armed_dry_run`
- `44m`: `paper`
- `8m`: `paper`
- `4m`: `paper`

All other lanes are disabled by default.

## Global Kill Switch Vs Per-Lane Mode

Per-lane mode is below the global live gates. A lane can be armed while global live execution remains disabled. That means:

- Lane arming does not override R102 final preflight.
- Lane arming does not override R106 first-live activation gate.
- Lane arming does not override the global kill switch.
- Lane arming does not replace human approval boundaries.

If a future config ever sets a lane to `tiny_live`, R122 still blocks it unless existing global live execution gates are ready. The lane is intent, not execution authority.

## What R122 Does Not Do

R122 does not:

- place orders
- create order payloads
- call Binance order endpoints
- enable live execution
- mutate env files
- expose secrets
- weaken R120 or R121 first-live readiness work
- make tiny-live easier than the existing global gates

The lane-control CLI reports hard safety fields:

```json
{"order_placed":false,"real_order_placed":false,"execution_attempted":false,"order_payload_created":false,"network_allowed":false,"secrets_shown":false}
```

## Operator Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward lane-control-status
```

The command returns compact JSON with lane summaries, active counts, future tiny-live eligible lanes, top blockers, and safety summary. It intentionally omits large live-eligibility recommendation arrays.

## Next Phases

- R123 fresh signal router: route fresh candidate/signal events into lane-control evaluation.
- R124 lane command interface: add operator commands to arm, disarm, and inspect lanes safely.
- R125 autonomous paper lane execution: allow armed paper lanes to execute paper-only paths.
- R126 first tiny-live lane execution: only after explicit authorization and existing global live gates are satisfied.
