# R124 Lane Command Interface

## Phase

`R124`

## Branch

`r124-lane-command-interface`

## Phase Classification

- Primary classification: WIRING / INTEGRATION
- Secondary classification(s): EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM

## Reason

R122 created lane-control intent and R123 routes fresh candidates into those lanes. R124 should add safe operator-facing controls for changing lane modes without creating execution authority or bypassing global gates.

## Main Objective

Add safe CLI/API/UI operator controls for changing a configured lane mode among:

- `disabled`
- `paper`
- `armed_dry_run`
- `tiny_live`

The interface must remain non-executing and must not make tiny-live easier than existing global gates.

## Capability Scan

Before implementation inspect:

- `src/app/hammer_radar/operator/lane_control.py`
- `src/app/hammer_radar/operator/fresh_signal_router.py`
- `configs/hammer_radar/lane_controls.json`
- `src/app/hammer_radar/operator/inspect.py`
- existing operator intent ledgers and approval API routes
- R102 final live preflight
- R106 first-live activation gate
- R122/R123 docs and tests

## Reuse / Extend / Create Decision

- Existing capability reused: R122 lane key normalization, lane config shape, and permission evaluation.
- Existing capability extended: inspect/operator surfaces for lane-mode changes.
- New capability created: a narrow lane command interface and audit record if needed.
- Why new code is necessary: R122 is read-only lane status and R123 is read-only routing; neither safely changes lane mode.
- Why this does not duplicate prior work: it should mutate only lane intent/config through a constrained operator path and continue to consume R122/R123 status surfaces.

## Safety Constraints

- Do not place orders.
- Do not create order payloads.
- Do not call Binance order endpoints.
- Do not enable live execution.
- Do not mutate env files.
- Do not bypass R102/R106/global gates.
- Do not expose secrets.
- Do not treat `tiny_live` lane mode as execution permission.
- Keep operator changes auditable.

## Expected Operator Behavior

R124 should require explicit lane tuple fields:

```text
symbol timeframe direction entry_mode mode
```

Mode changes should validate that the lane exists or explicitly report that no matching lane exists. A `tiny_live` mode should be accepted only as lane intent and must still report that global gates remain authoritative.

## Validation

Run focused tests for:

- valid mode transition
- invalid mode rejection
- unknown lane rejection
- tiny-live mode remains non-executing
- safety fields remain false
- CLI/API/UI response does not expose secrets
- R123 router behavior remains compatible after a lane mode update

## Do Not

- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not run `sudo`.
- Do not restart services.
