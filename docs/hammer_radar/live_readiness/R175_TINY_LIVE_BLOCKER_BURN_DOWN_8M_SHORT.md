# R175 Tiny-Live Blocker Burn-Down for BTCUSDT 8m Short

R175 creates one compact audit surface for the current `BTCUSDT|8m|short|ladder_close_50_618` tiny-live path.

It is audit-only. It does not promote the lane, write lane config, write risk-contract config, write env files, call Binance, create payloads, place orders, or enable live execution.

## Scope

R175 adds:

- `src/app/hammer_radar/operator/tiny_live_blocker_burn_down.py`
- `tiny-live-blocker-burn-down` in `src.app.hammer_radar.operator.inspect`
- `logs/hammer_radar_forward/tiny_live_blocker_burn_downs.ndjson` as an append-only audit ledger after exact confirmation

The burn-down composes existing local surfaces:

- lane mode from `configs/hammer_radar/lane_controls.json`
- risk-contract apply/draft state from `configs/hammer_radar/tiny_live_risk_contracts.json` and short risk ledgers
- fresh evidence from `short_paper_evidence_capture.ndjson`
- funding truth from `readonly_balance_checks.ndjson` and R174 sync records
- account-read role context from R173/R174 ledgers

## Commands

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-blocker-burn-down
```

Rejected recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-blocker-burn-down \
  --record-burn-down \
  --confirm-tiny-live-burn-down "wrong"
```

Record with exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-blocker-burn-down \
  --record-burn-down \
  --confirm-tiny-live-burn-down "I CONFIRM TINY LIVE BLOCKER BURN DOWN RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Expected Current State

For the current BTCUSDT 8m short family:

- `target_family.current_mode=paper`
- funding is blocked when the latest local balance truth is `ACCOUNT_NOT_FUNDED / 0.0 USDT`
- fresh evidence is blocked until capture count is at least 10
- risk contract remains draft/review-only and not applied for the 8m short target
- protective policy is reviewed but not live-applied
- operator approval is not present
- live flags remain disabled with kill-switch protection intact

The expected distance is `NOT_CLOSE_MULTIPLE_HARD_BLOCKERS` until funding, evidence, risk-contract apply, lane mode, approval, and arming blockers are cleared in later phases.

## Shortest Safe Path

1. Continue R157 until fresh captures are at least 10.
2. Fund the account later.
3. Rerun R158/R174 sync after evidence/funding changes.
4. Apply the risk contract only in a future safe config phase.
5. Build a tiny-live review packet.
6. Obtain explicit operator approval.
7. Run a future authorized arming phase.

## Do Not Run Yet

- `live-connector-submit`
- any order endpoint
- global live flag arming
- kill switch disable
- set short lane `tiny_live`
- write risk contract config
- transfer
- withdraw

## Safety Boundary

R175 safety remains:

- `env_written=false`
- `env_mutated=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `lane_config_written=false`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `signed_order_request_created=false`
- `signed_trading_request_created=false`
- `signed_readonly_request_created=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `transfer_endpoint_called=false`
- `withdraw_endpoint_called=false`
- `secrets_shown=false`
- `full_api_key_shown=false`
- `full_api_secret_shown=false`
- `global_live_flags_changed=false`
- `kill_switch_disabled=false`
- `paper_live_separation_intact=true`

## Next Phase

R176 should sync the exact fresh capture count from R157 records and determine whether the threshold of 10 has been met. It must not write config/env, call Binance, create payloads, or enable live execution.
