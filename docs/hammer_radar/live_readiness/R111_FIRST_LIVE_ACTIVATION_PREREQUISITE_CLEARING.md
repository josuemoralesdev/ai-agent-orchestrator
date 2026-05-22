# R111 First-Live Activation Prerequisite Clearing

Phase: R111

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## What R111 Adds

R111 adds a CLI-only prerequisite-clearing report over the existing R102-R110 readiness chain:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-prerequisite-clearing
```

The command returns JSON with:
- `PREREQS_BLOCKED` or `PREREQS_CLEARING_READY`
- source statuses from R102, R104, R105, R106, R109, and R110
- explicit prerequisite groups for the R110 blocker families
- evidence required, evidence present, owner, next action, and verification command per group
- cleared, blocked, operator-evidence-needed, and unknown counters
- prioritized next operator actions for today
- the morning live-readiness sequence
- safety booleans proving the phase is non-executing

R111 writes append-only evidence to:

```text
logs/hammer_radar_forward/first_live_prerequisite_clearing.ndjson
```

## What R111 Does Not Add

R111 does not add:
- live trading
- live env changes
- Binance order calls
- Binance account, funding, or balance calls
- approval-to-execution wiring
- Telegram-to-execution wiring
- a live order endpoint
- execution authority
- service restarts

It always reports:
- `live_ready=false`
- `execution_enabled_by_prereq_clearing=false`
- `order_placed=false`
- `execution_attempted=false`
- `real_order_possible=false`
- `secrets_shown=false`

## How R111 Uses R110 Burn-Down

R111 calls the R110 burn-down builder with recording disabled, then maps the R110 blocker groups into explicit prerequisite groups. R110 remains the launch-readiness burn-down planner. R111 is the audit layer that tells the operator which R110 groups are clear, blocked, need operator evidence, or remain unknown.

R111 reuses these source surfaces:
- R102 `final-live-preflight`
- R104 `tiny-live-armed-dry-run`
- R105 `one-tiny-live-order-protocol`
- R106 `first-live-activation-gate`
- R109 cockpit sacred button state
- R110 `first-live-burn-down`

R106 remains the activation authority. R111 does not replace it.

## Prerequisite Groups

R111 reports these groups:
- `candidate_freshness`
- `approval_records`
- `binance_credentials_presence`
- `account_funding_read_only_check`
- `protective_orders_readiness`
- `live_adapter_boundary`
- `tiny_position_size_cap`
- `max_loss_cap`
- `environment_flag_review`
- `confirmation_phrase_preparation`
- `sacred_button_safety`
- `duplicate_source_conflicts`

Each group includes:
- status: `CLEAR`, `BLOCKED`, `NEEDS_OPERATOR_EVIDENCE`, or `UNKNOWN`
- `evidence_required`
- `evidence_present`
- `next_action`
- `verification_command`
- `owner`
- `related_phase`
- `safety_notes`

## Evidence Required Per Group

Candidate freshness requires a fresh promoted candidate for the exact candidate id, risk contract hash, and packet hash.

Approval records require accepted approval intent and complete R85/R86/R88 human review records for the same candidate and hashes.

Binance credential presence requires private operator-managed presence booleans only. R111 must never print credential values.

Account/funding requires an operator read-only account/funding check record. R111 does not call account or balance APIs.

Protective readiness requires protective stop and take-profit readiness for the exact tiny-live candidate.

Live adapter boundary requires a reviewed adapter boundary with paper/live separation intact. R111 does not configure or call a live order adapter.

Tiny position size cap requires an explicit tiny notional cap for the first live candidate.

Max loss cap requires an explicit operator-acknowledged maximum loss cap.

Environment flag review requires safe live environment and kill-switch review. R111 does not edit flags.

Confirmation phrase preparation requires a prepared exact confirmation phrase template for a later explicit authorization phase. It remains inactive in R111.

Sacred button safety requires the R109 cockpit state to show `can_place_order=false` and `records_intent_only=true`.

Duplicate source conflicts require consistent source statuses from R102/R104/R105/R106/R109/R110.

## Morning Live-Readiness Sequence

1. Run first-live-burn-down
2. Confirm candidate freshness
3. Record approval intent
4. Complete R85/R86/R88 human review records
5. Configure Binance credential presence safely
6. Verify account/funding read-only
7. Verify protective order readiness
8. Verify adapter boundary
9. Define tiny size and max loss cap
10. Re-run final-live-preflight
11. Re-run tiny-live-armed-dry-run
12. Re-run one-tiny-live-order-protocol
13. Re-run first-live-activation-gate
14. Verify cockpit sacred button state
15. Stop if anything remains blocked

## Safety Constraints

- Do not place orders.
- Do not enable live trading.
- Do not call Binance order endpoints.
- Do not call Binance account or balance endpoints.
- Do not modify env flags.
- Do not wire approval buttons to execution.
- Do not create execution authority.
- Do not create a live order endpoint.
- Do not expose secrets.
- R106 remains authority.
- R109 sacred button remains intent-only.

## Why This Is Still Non-Executing

R111 reports prerequisite-clearing status only. It records an audit row and returns next operator actions, but it does not submit orders, create signed payloads, configure live adapters, call Binance, or change live flags.

Even if R111 eventually reports `PREREQS_CLEARING_READY`, the result is not live execution authority. It only means the prerequisite-clearing report sees no blocked, missing-evidence, or unknown groups. R106 still controls activation status, and a later explicit phase would still need separate authorization before any real order could be considered.

## How This Prepares R112

R111 identifies missing operator evidence with exact group names, owners, and verification commands. R112 should record the missing evidence safely:
- approval intent evidence
- human review evidence
- read-only funding evidence
- protective readiness evidence
- tiny size and max loss evidence

R112 should remain non-executing unless a later phase separately and explicitly authorizes live order placement.
