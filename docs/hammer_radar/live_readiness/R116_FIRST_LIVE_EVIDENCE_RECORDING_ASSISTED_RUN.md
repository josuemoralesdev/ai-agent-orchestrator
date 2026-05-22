# R116 First-Live Evidence Recording Assisted Run

Phase: R116

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R116 Adds

R116 adds a CLI-only assisted evidence-recording runner:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-assisted-run
```

It uses the R115 runbook sections and R114 generated evidence commands, then records selected evidence through the R112 evidence recorder only when the operator explicitly requests evidence-recording mode with the exact evidence-only confirmation phrase.

R116 writes an append-only assisted-run ledger at:

```text
logs/hammer_radar_forward/first_live_evidence_assisted_runs.ndjson
```

## What R116 Does Not Add

R116 does not add:
- live trading
- live env changes
- Binance order calls
- Binance account, funding, position, or balance calls
- evidence-to-execution wiring
- approval-to-execution wiring
- executable order payloads
- a live order endpoint
- execution authority
- service restarts

It always reports:
- `live_ready=false`
- `execution_enabled_by_assisted_run=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## Preview Mode

Preview mode is the default. It records no R112 evidence and only shows:
- selected evidence groups
- planned evidence types
- R115/R114 evidence commands that would be used
- R112/R113/R111/R110/R106/R109 recheck commands
- before and after safety/status snapshots
- stop conditions

Example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-assisted-run --group sacred_button_review
```

The preview status is `ASSISTED_RUN_PREVIEW` unless the requested group is unsupported, which returns `ASSISTED_RUN_REJECTED`.

## Execute-Evidence Mode

Evidence-recording mode is available only with both:

```bash
--execute-evidence
--confirm-evidence-only "I CONFIRM EVIDENCE RECORDING ONLY; NO LIVE ORDER; NO ENV CHANGE."
```

If the phrase is missing or different, the run returns `ASSISTED_RUN_REJECTED` and records no R112 evidence.

With the exact phrase, R116 parses the selected R115 evidence commands and calls the R112 evidence recorder directly. It does not shell out to the CLI and does not call execution code.

## Exact Confirmation Phrase

The exact phrase is:

```text
I CONFIRM EVIDENCE RECORDING ONLY; NO LIVE ORDER; NO ENV CHANGE.
```

This phrase authorizes evidence recording only. It is not live-order authorization and does not change R106 or R109 authority.

## Supported Groups

R116 supports these R115 evidence groups:
- `approval_records`
- `account_and_funding`
- `protective_orders`
- `adapter_boundary`
- `risk_limits`
- `environment_review`
- `sacred_button_review`
- `emergency_and_position_review`

Use `--group <group_name>` for one group or `--all-groups` for every supported group. With neither option, R116 previews all supported groups.

## Stop Conditions

R116 refuses evidence recording if any of these conditions are present:
- no active tuple
- active tuple is inconsistent
- R109 sacred button reports `can_place_order=true`
- any source reports `paper_live_separation_intact=false`
- any planned evidence command or note contains secret-looking values
- requested group is unsupported
- evidence-only confirmation is missing or invalid in execute mode
- R115 runbook reports unsafe state
- R106 status is unexpected or missing
- any safety field indicates execution, order placement, real-order possibility, or exposed secrets

## Ledger Location

R116 appends assisted-run summaries to:

```text
logs/hammer_radar_forward/first_live_evidence_assisted_runs.ndjson
```

Each ledger record includes:
- `event_type=FIRST_LIVE_EVIDENCE_ASSISTED_RUN`
- `assisted_run_id`
- `recorded_at_utc`
- status
- selected groups
- confirmation validity
- active tuple
- planned evidence types
- recorded evidence ids
- rejected evidence
- non-execution safety booleans
- source surfaces used

R112 remains the only evidence ledger writer for actual operator evidence records.

## Why Evidence Recording Is Not Execution

R116 only helps record audit evidence and recheck diagnostic status. It does not submit orders, create signed payloads, edit environment flags, configure live adapters, expose secrets, or authorize any order.

R106 remains the first-live activation gate authority. R109 remains an intent-only sacred button. Evidence recording can support later rechecks, but it cannot make a real order possible.

## How To Use R116 Safely Today

1. Run preview for the target group:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-assisted-run --group sacred_button_review
```

2. Verify the active tuple and planned evidence commands.
3. Confirm the operator personally verified the evidence outside R116.
4. Record only that group with the exact evidence-only phrase if appropriate:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-assisted-run --group sacred_button_review --execute-evidence --confirm-evidence-only "I CONFIRM EVIDENCE RECORDING ONLY; NO LIVE ORDER; NO ENV CHANGE."
```

5. Review the R112/R113/R106/R109 status snapshots in the output.
6. Stop if any blocker, unsafe field, secret warning, paper/live separation problem, or R106/R109 authority issue appears.

## How This Prepares R117

R116 creates an auditable assisted-run ledger and safely records selected evidence through R112. R117 should use that evidence trail to run post-evidence rechecks across R112, R113, R111, R110, R106, and R109, then report whether R106 blockers reduced.

R117 must remain non-executing unless a later phase explicitly authorizes execution.
