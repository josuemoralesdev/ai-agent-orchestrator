# R115 First-Live Evidence Recording Runbook

Phase: R115

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R115 Adds

R115 adds a CLI-only operator runbook and command pack for recording first-live evidence group by group using the R114 guided action pack:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-evidence-runbook
```

The command returns ordered runbook sections, grouped evidence commands, verification commands after each group, global stop conditions, a review-only bash script preview, and a next recheck sequence.

R115 writes append-only NDJSON to:

```text
logs/hammer_radar_forward/first_live_evidence_runbooks.ndjson
```

## What R115 Does Not Add

R115 does not add:
- live trading
- live env changes
- Binance order calls
- Binance account, funding, position, or balance calls
- evidence-to-execution wiring
- approval-to-execution wiring
- executable payloads
- a live order endpoint
- execution authority
- service restarts

It always reports:
- `live_ready=false`
- `execution_enabled_by_runbook=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## How It Uses R114

R115 calls R114 `first-live-evidence-guided-actions` as the source of evidence commands and active tuple state. R115 does not regenerate R114's evidence-command logic, does not create a second evidence ledger, and does not create a second readiness gate.

If R114 cannot produce a present active tuple, R115 returns `RUNBOOK_BLOCKED`. If R114 returns an action-ready tuple and paper/live separation is intact, R115 returns `RUNBOOK_READY`.

## Operator Sequence

1. Run `first-live-evidence-runbook`.
2. Verify `active_tuple.candidate_id`, `active_tuple.risk_contract_hash`, `active_tuple.packet_hash`, and `active_tuple.tuple_status`.
3. Review one runbook section at a time.
4. Run only the evidence commands for evidence the operator personally verified.
5. Run the section verification commands after each group.
6. Stop immediately on any stop condition.
7. After all selected evidence groups, run the final recheck sequence.
8. Treat R106 as the authority and R109 as intent-only.

## Command Sections

The runbook emits these ordered sections:

1. `tuple_verification`
2. `approval_records`
3. `account_and_funding`
4. `protective_orders`
5. `adapter_boundary`
6. `risk_limits`
7. `environment_review`
8. `sacred_button_review`
9. `emergency_and_position_review`
10. `final_recheck_sequence`

Each section includes:
- `section_id`
- `title`
- `purpose`
- `commands`
- `verification_commands`
- `stop_conditions`
- `safety_notes`

## Stop Conditions

Stop if any of these occur:
- candidate/hash tuple changed
- R106 gate reports unexpected status
- sacred button can_place_order true
- any output exposes secrets
- any output reports order_placed true
- any output reports execution_attempted true
- any Binance order endpoint appears in the flow
- any evidence note would include secrets
- any source reports paper_live_separation_intact false

## Script Preview Safety

`operator_script_preview` is marked `REVIEW_BEFORE_RUNNING`. It sets `set -euo pipefail`, echoes each section, runs evidence commands, and runs status/recheck commands after each group.

The preview is not automatically executed by R115. It is an operator review artifact only. It must not be used to bypass personal evidence verification.

The preview never calls Binance directly, never edits env flags, and never places orders.

## Ledger Location

R115 appends runbook records to:

```text
logs/hammer_radar_forward/first_live_evidence_runbooks.ndjson
```

Each record includes:
- `event_type=FIRST_LIVE_EVIDENCE_RUNBOOK`
- `runbook_id`
- `recorded_at_utc`
- `status`
- `active_tuple`
- `runbook_sections_count`
- `command_count`
- `stop_conditions`
- safety booleans
- source surfaces used

## Why This Is Non-Executing

R115 only prints R114/R112 evidence commands and R112/R113/R111/R110/R106/R109 verification commands. It does not call Binance, sign payloads, edit environment flags, submit orders, create execution endpoints, or wire evidence to execution.

R106 remains the first-live activation authority. R109 sacred button remains intent-only. No secret values should be pasted into evidence notes.

## How This Prepares R116

R115 creates the ordered, auditable command pack needed for an assisted evidence-recording run. R116 can let the operator choose which sections to record and may print or optionally run commands only after explicit user authorization, while still preserving no order placement, no live flag changes, and no Binance order endpoints.
