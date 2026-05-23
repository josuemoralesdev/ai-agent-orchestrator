# R123 Fresh Signal Router

## Phase

`R123`

## Branch

`r123-fresh-signal-router`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM

## Reason

R122 creates non-executing lane intent. R123 should route fresh candidate or signal events into lane-control evaluation so the system can decide whether a fresh event matches an armed lane before any later paper or tiny-live phase.

## Main Objective

Build a non-executing fresh-signal router that consumes existing candidate/signal sources, normalizes each event into:

```text
symbol | timeframe | direction | entry_mode
```

and evaluates it through `src.app.hammer_radar.operator.lane_control.evaluate_lane_permission`.

## Required Safety Constraints

- Do not place orders.
- Do not create order payloads.
- Do not call Binance order endpoints.
- Do not enable live execution.
- Do not mutate env files.
- Do not expose secrets.
- Do not treat lane arming as execution permission.
- Preserve R102/R106/global live gates.
- Keep Telegram/operator approval intent separate from execution.

## Capability Scan

Before implementation inspect:

- R122 lane-control config and module
- existing candidate and signal archive loaders
- strategy performance live eligibility
- candidate revalidation watch
- dual lane candidate watch
- notification watcher
- paper refresh scheduler
- inspect CLI patterns
- relevant tests under `tests/hammer_radar/`

## Expected Shape

R123 should produce a compact diagnostic router result with:

- generated time
- source event id
- normalized lane key
- lane-control evaluation result
- freshness verdict
- blockers
- safety fields showing no order, no payload, no execution, no network, and no secrets

## Validation

Run focused tests for the new router, compile changed Python files, and run the relevant Hammer Radar test subset. R123 remains non-executing unless a later phase explicitly authorizes execution.
