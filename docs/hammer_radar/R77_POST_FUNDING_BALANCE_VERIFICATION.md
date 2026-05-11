# R77 Post-Funding Balance Verification

Purpose: after funding, verify the operator-reported available USDT is enough
for the first controlled tiny live test while live execution remains disabled.

R77 is balance verification only. It does not call Binance, fund the account,
enable execution, or place orders.

## Manual Check

After funding the preferred initial amount, run:

```text
LIVE BALANCE CHECK 88
```

API equivalent:

```bash
curl --max-time 5 -s -X POST http://127.0.0.1:8015/live/funding-balance/check \
  -H 'Content-Type: application/json' \
  -d '{"available_usdt":88}' | jq .
```

## Interpretation

```text
available_usdt < 44      NOT_ENOUGH_BALANCE
44 <= available_usdt < 88 MARGINAL_BALANCE
88 <= available_usdt <=100 READY_AFTER_FUNDING
available_usdt > 100      READY_AFTER_FUNDING with over initial cap warning
```

The first live profile remains:

```text
margin_usdt=44
leverage=10
max_notional_usdt=444
margin_mode=ISOLATED
protective_orders_required=true
one_attempt_only=true
```

## Terminal Smoke

```bash
curl --max-time 5 -s http://127.0.0.1:8015/live/funding-balance/status | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/funding-balance/runbook | jq .
curl --max-time 5 -s -X POST http://127.0.0.1:8015/live/funding-balance/check \
  -H 'Content-Type: application/json' \
  -d '{"available_usdt":88}' | jq .
```

## Safety

- Keep `HAMMER_LIVE_EXECUTION_ENABLED=false`.
- Keep `HAMMER_ALLOW_LIVE_ORDERS=false`.
- Keep `HAMMER_GLOBAL_KILL_SWITCH=true`.
- Do not use 444/888 funding or margin tiers yet.
- Balance verification is not execution.
- Next gate is R78 rehearsal/test-order/protective readiness.

## Rollback

If behavior is unexpected:

- Keep execution off.
- Keep the kill switch active.
- Withdraw extra funds or keep account unfunded.
- Disable policy env switches if needed.
