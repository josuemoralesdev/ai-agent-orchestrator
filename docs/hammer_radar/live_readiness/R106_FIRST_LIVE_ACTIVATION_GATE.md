# R106 First-Live Activation Gate

Phase: R106

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## 1. What R106 Adds

R106 adds a CLI-only first-live activation gate:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-activation-gate
```

The gate composes:
- R102 final live preflight
- R103 Telegram final approval intent evidence
- R104 tiny-live armed dry-run result
- R105 one tiny live order protocol check

It returns `FIRST_LIVE_BLOCKED` or `FIRST_LIVE_ACTIVATION_READY`.

## 2. What R106 Does Not Add

R106 does not add:
- live trading
- live env changes
- order placement
- Binance order calls
- signed order payload creation
- Telegram approval-to-execution wiring
- live execution authority
- a live order endpoint
- an approval API endpoint

## 3. Why R106 Does Not Place Orders

R106 is the final gate before a separately authorized execution phase. It only reads and records evidence from existing readiness surfaces.

R106 always returns:
- `live_ready=false`
- `execution_enabled_by_gate=false`
- `order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`

## 4. Exact Command To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-activation-gate
```

No-record preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-activation-gate --no-record
```

## 5. Example FIRST_LIVE_BLOCKED Output

Shape:

```json
{
  "status": "FIRST_LIVE_BLOCKED",
  "live_ready": false,
  "execution_enabled_by_gate": false,
  "order_placed": false,
  "execution_attempted": false,
  "real_order_possible": false,
  "final_preflight_status": "BLOCKED",
  "tiny_live_armed_dry_run_status": "BLOCKED_FOR_DRY_RUN",
  "one_tiny_live_order_protocol_status": "PROTOCOL_BLOCKED",
  "approval_intent_present": false,
  "approval_intent_status": "MISSING",
  "blockers": [
    "final preflight is not READY",
    "tiny-live armed dry run is not READY_FOR_DRY_RUN",
    "one tiny live order protocol is not PROTOCOL_PREREQS_READY",
    "approval intent missing",
    "operator confirmation phrase missing"
  ]
}
```

The actual output includes hashes, live flag states, connector mode, sanitized credential presence booleans, protective readiness, source surfaces, and ledger path.

## 6. Meaning Of FIRST_LIVE_ACTIVATION_READY

`FIRST_LIVE_ACTIVATION_READY` means:

```text
All prerequisites are satisfied for a future explicitly authorized first-live execution phase.
```

It does not mean an order may be placed by R106. It does not make the system `LIVE_READY`.

## 7. Required Blockers Before Future Execution

R106 returns `FIRST_LIVE_BLOCKED` if any of these remain:

- Final preflight is not `READY`.
- Tiny-live armed dry run is not `READY_FOR_DRY_RUN`.
- R105 protocol is not `PROTOCOL_PREREQS_READY`.
- Approval intent is missing or not accepted.
- Candidate id is missing.
- Candidate is stale.
- Risk contract hash is missing or mismatched.
- Packet hash is missing or mismatched.
- Human approval record is missing.
- Binance credentials are missing.
- Connector/account boundary is not reviewed.
- Protective orders are not ready.
- Live order adapter is not configured.
- Global kill switch state is unsafe or ambiguous.
- Live execution flag state is unsafe or ambiguous.
- Live orders flag state is unsafe or ambiguous.
- Open/conflicting position status is unknown.
- Account balance/funding is unknown.
- Position size cap is unknown.
- Max loss cap is unknown.
- Duplicate readiness source conflict is detected.
- Paper/live separation is not intact.
- Operator confirmation phrase is missing.

## 8. Confirmation Phrase Requirement

R106 requires the future confirmation phrase template from R105:

```text
I CONFIRM ONE TINY LIVE ORDER FOR <candidate_id> WITH RISK <risk_contract_hash> AND PACKET <packet_hash>; MAX LOSS <amount>; I UNDERSTAND THIS CAN LOSE REAL MONEY.
```

R106 does not activate this phrase for execution. It only reports that the phrase is required and currently missing unless a future safe confirmation record exists.

## 9. Ledger Location

R106 records append-only evidence under:

```text
first_live_activation_gate_checks.ndjson
```

Each record includes status, blockers, warnings, hashes, final preflight status, R104/R105 statuses, approval-intent state, live flags, connector mode, safety booleans, and source surfaces.

## 10. How R106 Prepares The Future First-Live Execution Phase

R106 creates the final non-executing evidence gate. A future execution phase may only be considered if:
- R106 returns `FIRST_LIVE_ACTIVATION_READY`.
- The user explicitly authorizes the execution phase.
- The future phase still preserves protective order, kill-switch, confirmation, postmortem, and one-order-only requirements.

## 11. Safety Constraints

R106 must preserve:
- no live orders
- no Binance order endpoint calls
- no account or balance calls
- no env edits
- no secret exposure
- no Telegram approval-to-execution wiring
- no executable payload creation
- no live order endpoint
- paper/live separation
- `live_ready=false`
- `execution_enabled_by_gate=false`
- `order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
