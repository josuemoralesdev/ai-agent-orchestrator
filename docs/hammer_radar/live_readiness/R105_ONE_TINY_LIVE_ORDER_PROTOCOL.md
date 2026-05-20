# R105 One Tiny Live Order Protocol

Phase: R105

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## 1. Executive Summary

R105 defines protocol only.

R105 does not place orders, enable live execution, wire execution, create a live order endpoint, or make the system `LIVE_READY`.

R105 adds an optional protocol checker that can report `PROTOCOL_BLOCKED` or `PROTOCOL_PREREQS_READY`. Even `PROTOCOL_PREREQS_READY` is not live readiness and does not authorize execution.

## 2. Absolute Non-Bypassable Gates

A future one tiny live order may only be considered if all are true:

- Final preflight status is `READY`.
- Tiny-live armed dry run status is `READY_FOR_DRY_RUN`.
- `live_ready` is still false until the final human activation step.
- Exactly one fresh promoted candidate exists.
- Candidate is not stale.
- `candidate_id` is known.
- Risk contract hash is present and matches the candidate.
- Final review packet hash is present and matches the candidate.
- Human approval record exists and matches the candidate/hash tuple.
- Telegram approval intent exists and matches the candidate/hash tuple.
- Binance credentials are present without exposing values.
- Connector/account boundary is explicitly reviewed.
- Live execution flag state is intentionally reviewed.
- Live orders flag state is intentionally reviewed.
- Global kill switch state is intentionally reviewed.
- Protective orders are configured and ready.
- Live order adapter is configured but not yet used.
- Position size is tiny and explicitly capped.
- Max loss is explicitly capped.
- No open conflicting BTCUSDT position exists.
- Account balance/funding was checked.
- Dry-run ledger has a fresh successful record.
- Operator typed the exact confirmation phrase.
- Post-order monitoring plan exists.
- Emergency cancel/kill-switch plan exists.

If any item is missing, ambiguous, stale, mismatched, or disputed by another readiness surface, the protocol is blocked.

## 3. Forbidden Conditions

The protocol forbids a live order if:

- Any blocker remains.
- Candidate is stale.
- Hashes mismatch.
- Approval intent is missing.
- Final review is missing.
- Protective orders are not ready.
- Kill switch state is ambiguous.
- Binance account/funding is unknown.
- Position size cannot be proven tiny.
- Order adapter behavior cannot be proven safe.
- There is any duplicate readiness source conflict.
- Telegram approval is being treated as execution authority.
- Final preflight is not `READY`.
- Tiny-live armed dry run is not `READY_FOR_DRY_RUN`.
- The operator has not completed the exact final confirmation phrase.
- R106 or a later explicitly authorized activation phase has not approved execution.

## 4. Exact Future Confirmation Phrase Format

The future final confirmation phrase template is:

```text
I CONFIRM ONE TINY LIVE ORDER FOR <candidate_id> WITH RISK <risk_contract_hash> AND PACKET <packet_hash>; MAX LOSS <amount>; I UNDERSTAND THIS CAN LOSE REAL MONEY.
```

This phrase is documented only. R105 does not make it active for execution.

## 5. One Tiny Order Limits

Recommended protocol limits:

- One order only.
- BTCUSDT only unless the risk contract config explicitly says otherwise.
- Minimum viable position size.
- Isolated margin preferred if applicable.
- No averaging down.
- No martingale.
- No second order until postmortem is completed.
- No scaling after first win.
- No revenge trade after first loss.
- Stop immediately after one loss or any safety discrepancy.
- No new live attempt if protective orders cannot be verified.

## 6. Operator Runbook

Future sequence:

1. Run final-live-preflight:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-live-preflight
```

2. Run tiny-live-armed-dry-run:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-armed-dry-run
```

3. Run R105 protocol checker:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward one-tiny-live-order-protocol
```

4. Verify candidate freshness.
5. Verify risk contract hash.
6. Verify packet hash.
7. Verify approval intent.
8. Verify Binance account/funding manually; do not print secrets.
9. Verify protective order readiness.
10. Verify kill switch and emergency plan.
11. Type the final confirmation phrase only in a future authorized activation phase.
12. Place exactly one tiny order only in a future authorized phase.
13. Immediately verify order and protective state.
14. Record postmortem.

## 7. Postmortem Requirements

After the future first live order, the protocol requires:

- Order id.
- Timestamp.
- Entry.
- Stop.
- Take profit.
- Size.
- Max risk.
- Fees/slippage.
- Whether protective orders were attached.
- Whether alert/ledger matched execution.
- Whether system behaved as expected.
- Whether human behavior stayed disciplined.
- Result.
- Lessons.
- Go/no-go for any second order.

No second order may be considered until postmortem is complete.

## 8. Rollback / Emergency

Emergency requirements:

- Keep global kill switch available and reviewed before activation.
- If a service action is needed, the operator must run it manually; Codex must not start, stop, restart, enable, or disable systemd services without explicit approval.
- If the repo exposes a safe connector cancel surface in a future phase, use it only under the authorized protocol for the exact order id.
- Manually verify open orders and position state in the exchange UI or authorized account-status workflow.
- Stop any future polling/execution service if it is producing unsafe behavior; use operator-approved systemd commands only.
- No further orders until review.

Current known service check commands for operator review:

```bash
systemctl status hammer-approval-api.service --no-pager
systemctl status hammer-telegram-polling.service --no-pager
systemctl status hammer-paper-refresh.service --no-pager
```

R105 does not run these commands.

## 9. How R105 Prepares R106

R106 may become the explicit first-live activation gate only if the R105 protocol checker says all prerequisites are satisfied.

R106 must still be separately authorized before any live execution, env flag change, Binance order call, order adapter activation, or final confirmation phrase handling becomes executable.

## Protocol Checker

Command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward one-tiny-live-order-protocol
```

The checker returns:
- `status=PROTOCOL_BLOCKED` or `PROTOCOL_PREREQS_READY`
- `live_ready=false`
- `execution_enabled_by_protocol=false`
- `order_placed=false`
- `execution_attempted=false`
- blockers
- warnings
- final preflight status
- tiny-live armed dry-run status
- approval intent presence/status
- candidate id
- risk contract hash
- packet hash
- inactive confirmation phrase template
- source surfaces used

Ledger:

```text
one_tiny_live_order_protocol_checks.ndjson
```

The ledger is append-only evidence. It is not execution authority.
