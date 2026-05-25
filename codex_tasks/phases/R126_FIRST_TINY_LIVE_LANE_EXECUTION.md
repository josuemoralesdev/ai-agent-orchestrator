# R126 First Tiny-Live Lane Execution

## Phase

`R126`

## Branch

`r126-first-tiny-live-lane-execution`

## Phase Classification

- Primary classification: NEW CAPABILITY
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk level: HIGH

## Reason

R125 creates autonomous paper lane execution records for fresh routed candidates. R126 should design the first tiny-live lane execution path only after the paper lane has proven the lane-control and routing workflow without any real orders.

## Main Objective

Design the first tiny-live lane execution path for one explicitly configured lane, with R106/global gates ready and operator confirmation required before any future live action.

## Preconditions

- R125 paper lane execution works and has auditable paper records.
- A fresh R123 routed candidate exists.
- R106/global first-live activation gates are ready.
- The target lane is explicitly configured for the future tiny-live path.
- Operator gives explicit live confirmation in the future R126 turn.
- Protective order requirements, max loss limits, rollback plan, monitoring, and postmortem plan are defined.

## Safety Constraints

- Do not implement live execution in R125.
- Do not place orders unless the future R126 task and current operator instruction explicitly authorize that exact live behavior.
- Do not create Binance order payloads during design-only work.
- Do not call Binance order endpoints during design-only work.
- Do not send signed requests during design-only work.
- Do not mutate env files.
- Do not enable global live execution.
- Do not bypass R106/global gates.
- Do not weaken R120/R121/R122/R123/R124/R125 safety boundaries.

## Capability Scan

Before implementation, inspect:

- R102 final live preflight
- R106 first-live activation gate
- R122 lane control
- R123 fresh signal router
- R124 lane command interface
- R125 autonomous paper lane execution
- existing execution safety modules
- existing live execution preview and intent modules
- existing Binance connector boundaries
- existing tests for live safety and execution adapters

## Expected Output

R126 must produce a scoped design and implementation plan for the first tiny-live lane path. It must preserve paper/live separation and identify every gate, confirmation, protective-order check, and rollback step required before any real order can be considered.

## Do Not Implement In R125

R126 is intentionally not implemented as part of R125. R125 may only create paper lane execution records and paper shadows for tiny-live lanes.
