# R79.1 Active Timeframe Review Policy

## Purpose

R79.1 preserves fresh `22m` and `55m` Hammer Radar candidates as active selected-review candidates. They are no longer discarded solely because they are outside the tiny `13m` / `44m` profile.

This phase is policy review only. It does not place orders, enable live execution, edit env files, call Binance, or bypass any safety gate.

## Policy

`22m` and `55m` use the `ACTIVE_SELECTED_REVIEW` profile:

- margin: `44 USDT`
- leverage: `10`
- max notional: `444 USDT`
- margin mode: `ISOLATED`
- protective orders required: yes
- one attempt only: yes
- explicit selection required: yes
- exact `LIVE APPROVE <signal_id>` required: yes
- `LIVE INTENT`, rehearsal, test-order validation, protective readiness, and final gate still required

Freshness cutoffs:

- `22m`: `22.5` minutes
- `55m`: `55.5` minutes

## Default State

By default, active timeframe live approval is disabled:

```text
HAMMER_ACTIVE_TIMEFRAME_LIVE_ALLOWED=false
HAMMER_ACTIVE_TIMEFRAME_LIVE_TIMEFRAMES=22m,55m
```

Fresh active candidates remain selectable and reviewable, but `FIRST LIVE NEXT` must not emit `LIVE APPROVE` while active policy is disabled.

## Manual Policy Enablement

To allow selected active candidates through approval and intent review, an operator may manually set:

```text
HAMMER_ACTIVE_TIMEFRAME_LIVE_ALLOWED=true
HAMMER_ACTIVE_TIMEFRAME_LIVE_TIMEFRAMES=22m,55m
```

After any manual env edit, restart the approval API and Telegram polling services manually, then smoke:

```text
curl --max-time 5 -s http://127.0.0.1:8015/live/timeframe-policy/status | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/policy-arming/status | jq .
curl --max-time 5 -s http://127.0.0.1:8015/live/first-candidates/status | jq .
```

R79.1 does not perform these edits or restarts.

## Operator Flow

```text
FIRST LIVE TIMEFRAME POLICY
FIRST LIVE CANDIDATES
FIRST LIVE SELECT <22m_or_55m_signal_id>
FIRST LIVE SELECTED
FIRST LIVE NEXT
LIVE APPROVE <signal_id>
LIVE INTENT <signal_id>
LIVE REHEARSAL <intent_id>
FIRST LIVE TEST ORDER <executor_rehearsal_id>
FIRST LIVE PROTECTIVE CHECK
LIVE FINAL GATE
```

## Difference From Tiny Live

`13m` and `44m` remain tiny-live review timeframes. They can be offered for approval without explicit queue selection when fresh and compatible.

`22m` and `55m` require explicit selection and active policy enablement before approval can progress.

## Safety Chain

Active timeframe review still requires:

```text
approval -> intent -> rehearsal -> test-order -> protective -> final gate
```

No naked entry is allowed. Protective stop-loss and take-profit readiness remain mandatory before any future live arming phase.

## Future Gates

Markov Regime Gate and Miro Fish Gate remain future quality gates before real execution scaling. They should be added before increasing live exposure, and may be added before or after R80 depending on whether R80 remains one-attempt, microscopic, and manually armed.
