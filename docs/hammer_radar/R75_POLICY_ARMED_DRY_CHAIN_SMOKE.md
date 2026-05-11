# R75 Policy-Armed Dry Chain Smoke

Purpose: verify that policy-armed micro and higher-timeframe candidates can
enter the first-live approval and intent chain while execution remains blocked.

R75 is dry-chain only. It does not fund accounts, edit env files, restart
services, call Binance, place orders, or enable live execution.

## What R75 Proves

- A queue-fresh selected `4m` or `8m` BTCUSDT long candidate can become
  approval-eligible when micro policy is simulated as armed.
- A queue-fresh selected `444m` or `4H` BTCUSDT long candidate can become
  approval-eligible when higher-timeframe policy is simulated as armed.
- `FIRST LIVE NEXT` can move from approval to intent and then to rehearsal as
  a dry chain state.
- `order_placed=false`, `real_order_placed=false`, and
  `execution_attempted=false` remain enforced.

## What R75 Does Not Prove

- It does not prove live orders can be placed.
- It does not validate funds.
- It does not validate final live execution arming.
- It does not replace R52 intent, R53 rehearsal, payload readiness, test-order
  validation, manual env/funds arming, or final gate.

## API Commands

```bash
curl --max-time 5 -s http://127.0.0.1:8015/live/policy-dry-chain/status | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/policy-dry-chain/runbook | jq .

curl --max-time 10 -s -X POST http://127.0.0.1:8015/live/policy-dry-chain/check \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"micro"}' | jq .

curl --max-time 10 -s -X POST http://127.0.0.1:8015/live/policy-dry-chain/check \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"higher"}' | jq .

curl --max-time 10 -s -X POST http://127.0.0.1:8015/live/policy-dry-chain/check \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"both"}' | jq .
```

## Telegram Commands

```text
LIVE POLICY DRY SMOKE
LIVE MICRO DRY SMOKE
LIVE HIGHER DRY SMOKE
LIVE POLICY DRY RUNBOOK
```

## Expected Blocked States

If no queue-fresh candidate exists, R75 returns `BLOCKED` with one of:

```text
no queue-fresh micro candidate available
no queue-fresh higher-timeframe candidate available
```

That is a safe result. It means the dry chain did not fabricate a signal.

## Safety Guarantees

- Policy env may be simulated in process for evaluation only.
- Service env files are not edited.
- Previous selected candidate state is restored after the smoke.
- Approval and dry intent records are exact signal-bound and marked with
  `r75_policy_armed_dry_chain_smoke`.
- Binance live network is not called.
- No order placement path is added.

## Transition To R76

Before funding or the first live tiny test, R76 should verify funding readiness,
manual execution arming boundaries, final test-order validation, and rollback
steps while keeping the first funded test tiny.
