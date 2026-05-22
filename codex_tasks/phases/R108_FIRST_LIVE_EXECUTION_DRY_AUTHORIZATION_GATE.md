# R108 First-Live Execution Dry Authorization Gate

Phase: R108

Status: FUTURE DRAFT TASK ONLY

Branch: `r108-first-live-execution-dry-authorization-gate`

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

Assigned agents:
- builder
- index
- qa
- security

## Main Objective

Create a dry authorization gate for the future first-live execution phase. R108 must verify the R107 design checklist and current R106 activation evidence without placing an order or enabling live trading.

R108 is dry authorization only. It is not execution authority.

## Non-Execution Rule

R108 must not:
- place orders
- enable live trading
- call Binance order endpoints
- call Binance account, funding, balance, position, or open-order endpoints unless a future task explicitly authorizes a read-only check
- modify env flags
- wire Telegram approval to execution
- create a live order endpoint
- create executable live payloads
- create execution authority

## Required Inputs

R108 must inspect:
- `docs/hammer_radar/live_readiness/R107_FIRST_LIVE_EXECUTION_PHASE_DESIGN.md`
- `configs/hammer_radar/first_live_execution_design_checklist.json`
- `docs/hammer_radar/live_readiness/R106_FIRST_LIVE_ACTIVATION_GATE.md`
- the existing R102-R106 inspect command surfaces
- relevant tests for final preflight, final approval intent, tiny-live armed dry-run, one tiny live order protocol, and first-live activation gate

## Required Preconditions

R108 may only report dry authorization readiness if:
- `final-live-preflight` is `READY`
- `tiny-live-armed-dry-run` is `READY_FOR_DRY_RUN`
- `one-tiny-live-order-protocol` is `PROTOCOL_PREREQS_READY`
- `first-live-activation-gate` is `FIRST_LIVE_ACTIVATION_READY`
- R107 checklist exists and validates as JSON
- R107 design document exists
- Candidate id, risk contract hash, packet hash, Telegram approval intent, and human approval records match across the status chain

If any prerequisite is missing, stale, blocked, mismatched, or ambiguous, R108 must report dry authorization blocked.

## Expected Artifact

R108 may add a non-executing dry authorization checker only if it is clearly safer than manual inspection and reuses the existing R102-R106 surfaces. The checker must:
- read existing evidence only
- never place orders
- never call Binance order endpoints
- never call account/balance endpoints without explicit future authorization
- never enable live flags
- report safety booleans
- return a blocked status unless every prerequisite is satisfied

Suggested command name if implemented:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-execution-dry-authorization-gate
```

The command name is a suggestion only. R108 may remain documentation/config-only if a new checker would duplicate existing R106 authority.

## Validation

If docs/config only:

```bash
git diff --check
.venv/bin/python - <<'PY'
import json
from pathlib import Path
json.load(Path("configs/hammer_radar/first_live_execution_design_checklist.json").open())
PY
scripts/hammer_radar/list_live_readiness_phases.sh
```

If Python is changed:

```bash
PYTHONPATH=. .venv/bin/python -m py_compile <modified_python_files>
PYTHONPATH=. .venv/bin/python -m pytest -q <focused_tests>
```

## Safety Constraints

R108 must preserve:
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`
- live execution disabled unless a later explicit execution phase authorizes otherwise
- Telegram approval as intent only
- paper/live separation
- kill switch and rollback review discipline

## Recommended Next Phase

Only after R108 passes as dry authorization may the operator consider drafting a separate future explicitly authorized first-live execution phase. That future phase must still require current-turn user authorization before any order placement or Binance order endpoint call.

