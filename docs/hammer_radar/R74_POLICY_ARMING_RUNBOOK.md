# R74 Policy Arming Runbook

Purpose: make micro and higher-timeframe first-live policy arming explicit,
inspectable, smoke-tested, and reversible before funding or live tests.

R74 is policy arming only. It does not enable live order execution, does not
place orders, does not edit env files, and does not restart services.

## Current Safe Defaults

Default runtime policy:

```text
HAMMER_MICRO_LIVE_ALLOWED=false
HAMMER_MICRO_LIVE_TIMEFRAMES=4m,8m
HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=false
HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES=444m,4H
```

Expected execution safety remains separate:

```text
HAMMER_LIVE_EXECUTION_ENABLED=false
HAMMER_ALLOW_LIVE_ORDERS=false
HAMMER_GLOBAL_KILL_SWITCH=true
HAMMER_PROTECTIVE_ORDERS_ENABLED=false
HAMMER_PROTECTIVE_ORDER_MODE=PREVIEW_ONLY
```

## Enable Micro Policy Only

Edit the env file used by `hammer-approval-api.service`. Current known service
configuration uses:

```text
EnvironmentFile=/home/josue/.config/hammer-radar/binance-readonly.env
EnvironmentFile=/home/josue/.config/hammer-radar/notifications.env
```

Suggested policy-only switches:

```text
HAMMER_MICRO_LIVE_ALLOWED=true
HAMMER_MICRO_LIVE_TIMEFRAMES=4m,8m
HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=false
```

## Enable Higher-Timeframe Policy Only

```text
HAMMER_MICRO_LIVE_ALLOWED=false
HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=true
HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES=444m,4H
```

## Enable Both

```text
HAMMER_MICRO_LIVE_ALLOWED=true
HAMMER_MICRO_LIVE_TIMEFRAMES=4m,8m
HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=true
HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES=444m,4H
```

## Restart

Restart manually after env edits:

```bash
sudo systemctl restart hammer-approval-api.service
sudo systemctl restart hammer-telegram-polling.service
```

## Smoke Checks

```bash
curl --max-time 5 -s http://127.0.0.1:8015/health | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/timeframe-policy/status | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/policy-arming/status | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/policy-arming/runbook | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/first-candidates/status | jq .
```

Telegram smoke:

```text
LIVE POLICY ARMING
LIVE MICRO ARMING
LIVE HIGHER ARMING
FIRST LIVE TIMEFRAME POLICY
FIRST LIVE NEXT
```

Expected policy-only result:

```text
order_placed=false
real_order_placed=false
secrets_shown=false
```

## Rollback

Restore policy switches:

```text
HAMMER_MICRO_LIVE_ALLOWED=false
HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=false
```

Restart both services again and verify `/live/policy-arming/status` reports
micro and higher policy disabled.

## Safety Notes

- Enabling policy is not execution.
- Selecting a signal is not execution.
- Approval is not execution.
- Live execution flags remain separate from R74 policy arming.
- Funding should wait until policy arming smoke passes.
- The first funded test should remain tiny and still pass R52 intent, R53
  rehearsal, payload readiness, test-order validation, manual arming, and final
  gate.
