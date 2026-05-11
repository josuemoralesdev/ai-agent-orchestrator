# R76 Funded Tiny Live Readiness

Purpose: decide whether controlled tiny test capital can be deposited for the
first live test path while live execution remains disabled.

R76 is a checklist only. It does not fund the account, edit env files, restart
services, call Binance live endpoints, or place orders.

## What Funding Readiness Means

`READY_TO_FUND` means the system posture is suitable to deposit limited tiny
test capital for a later controlled live test. It does not mean the system is
ready to place a live order.

## What It Does Not Mean

- It does not enable live trading.
- It does not approve a live order.
- It does not replace R52 intent, R53 rehearsal, payload readiness, test-order
  validation, protective readiness, manual env/funds review, or final gate.
- It does not prove account balance unless the operator verifies balance
  manually or through a known safe readonly checker.

## Funding Amount

Recommended initial funding:

```text
25-50 USDT minimum operational test
88 USDT preferred initial tiny test funding
100 USDT maximum initial funding cap
Do not fund 444/888 USDT tiers yet
```

First live attempt profile remains:

```text
margin_usdt=44
leverage=10
max_notional_usdt=444
margin_mode=ISOLATED
protective_orders_required=true
one_attempt_only=true
```

## Pre-Funding Checklist

Run or verify:

```bash
systemctl is-active hammer-approval-api.service
systemctl is-active hammer-telegram-polling.service
systemctl is-active hammer-paper-refresh.service
systemctl is-active radar.service

curl --max-time 5 -s http://127.0.0.1:8015/health | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/timeframe-policy/status | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/policy-arming/status | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/policy-dry-chain/status | jq .
curl --max-time 10 -s -X POST http://127.0.0.1:8015/live/policy-dry-chain/check \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"micro"}' | jq .
```

If higher timeframe policy is planned, also run:

```bash
curl --max-time 10 -s -X POST http://127.0.0.1:8015/live/policy-dry-chain/check \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"higher"}' | jq .
```

Verify:

```text
order_placed=false
real_order_placed=false
execution_attempted=false
secrets_shown=false
HAMMER_LIVE_EXECUTION_ENABLED=false
HAMMER_ALLOW_LIVE_ORDERS=false
HAMMER_GLOBAL_KILL_SWITCH=true
```

## Funding Action

Deposit only controlled tiny test capital:

```text
Preferred: 88 USDT
Minimum operational test: 25-50 USDT
Do not deposit 444/888 USDT tiers yet
```

Do not enable live execution during or immediately after deposit.

## Post-Funding Checklist

- Verify balance manually in Binance UI or a known safe readonly checker.
- Run `LIVE FUNDING CHECK` again.
- Wait for an exact fresh candidate.
- Walk the chain manually:
  - R52 intent
  - R53 rehearsal
  - payload readiness
  - test-order validation
  - protective readiness
  - manual env/funds review
  - final protected gate

## Rollback / Safety

- Keep `HAMMER_LIVE_EXECUTION_ENABLED=false`.
- Keep `HAMMER_ALLOW_LIVE_ORDERS=false`.
- Keep `HAMMER_GLOBAL_KILL_SWITCH=true`.
- Disable policy env switches if behavior is unexpected.
- Stop before any live order if order flags, execution flags, or dry-smoke
  safety flags are not clean.

## Telegram

```text
LIVE FUNDING READINESS
LIVE FUNDING RUNBOOK
LIVE FUNDING CHECK
```
