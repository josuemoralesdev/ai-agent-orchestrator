# R103 Telegram Final Approval Flow

Phase: R103

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT, DUPLICATE RISK
- Duplicate risk level: HIGH

Purpose: add a Telegram-facing final preflight and approval-intent flow that reuses the R102 final live preflight adapter. This phase is record-only and non-executable.

## 1. What R103 Adds

R103 extends the existing Telegram operator bridge with:
- `/final_preflight`
- `/approve_final <candidate_id> <risk_contract_hash> <packet_hash>`

`/final_preflight` calls the R102 final live preflight adapter and returns a compact Telegram-safe summary:
- `READY` or `BLOCKED`
- top blockers
- risk contract hash when available
- final review packet hash when available
- live execution flag state
- live order flag state
- global kill switch state
- connector mode

`/approve_final ...` validates the command shape, compares supplied hashes against the current R102 final preflight output, and records a final approval intent under the Hammer Radar log directory:

```text
final_approval_intents.ndjson
```

## 2. What R103 Does Not Add

R103 does not add:
- live trading
- live env changes
- live arming
- order placement
- signed order payload creation
- Binance order or account calls
- Telegram approval-to-execution wiring
- a new readiness source of truth

Approval intent is not execution permission.

## 3. Telegram Command Examples

Request final preflight:

```text
/final_preflight
```

Record approval intent:

```text
/approve_final normal|BTCUSDT|13m|long|ladder_close_50_618 <risk_contract_hash> <packet_hash>
```

Malformed approval commands are rejected and do not record an intent.

## 4. Approval-Intent Semantics

The approval intent record includes:
- `event_type=FINAL_APPROVAL_INTENT`
- `recorded_at_utc`
- candidate id
- supplied risk contract hash
- supplied packet hash
- expected hashes from final preflight
- hash match results
- final preflight status
- blockers
- Telegram chat/user identifier when safely available
- live execution flags
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`

If hashes mismatch or expected hashes are unavailable, the intent is recorded as rejected. If hashes match but final preflight is `BLOCKED`, the intent is recorded as blocked and ineffective.

## 5. Why Telegram Is Not Authority

Telegram is only an operator input and status surface. It can request the current final preflight and record that the operator supplied a candidate id and hashes, but it cannot:
- arm live execution
- override blockers
- bypass stale-candidate protection
- override the global kill switch
- place or authorize an order by itself

## 6. How Final Preflight Remains Authority

R103 uses `operator.final_live_preflight.build_final_live_preflight` for current status, hashes, blockers, flags, connector mode, Telegram configuration, and paper/live separation. The Telegram flow does not recompute readiness independently.

The Telegram payload includes `source_surfaces_used` with the final preflight adapter and the underlying R102 readiness surfaces.

## 7. Safety Constraints

R103 preserves:
- no live order from signal alone
- no live order from Telegram alert alone
- no live order from Telegram approval intent alone
- no live order without matching risk contract hash
- no live order without matching final review packet hash
- no live order when final preflight is blocked
- no live order if candidate is stale
- no live order if environment boundary is blocked
- no live order if live execution flags disagree
- no live order if Binance boundary/status is unsafe
- no live order if global kill switch blocks execution
- no secret exposure
- no Binance order endpoint calls

## 8. How This Prepares R104

R104 can use the R103 records to run a tiny-live armed dry run that proves the operator path, hash matching, final preflight blockers, and audit trail remain coherent while still avoiding live order placement.

Before R104, the operator still needs to resolve the R102/R101 blockers, including missing review records, blocked live env boundary, dry-run connector mode, missing Binance credentials, protective readiness false, and active kill switch.
