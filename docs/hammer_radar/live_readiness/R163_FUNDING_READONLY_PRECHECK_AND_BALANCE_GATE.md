# R163 Funding Readonly Precheck and Balance Gate

Phase: R163

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R163 Follows R162

R159, R160, and R162 all left funding as a blocker for the future BTCUSDT 8m short tiny-live review path:

```text
BTCUSDT|8m|short|ladder_close_50_618
```

R162 reviewed the risk-contract apply path and kept it blocked because evidence, funding, operator approval, and config-write authorization were not present. R163 isolates only the funding question and keeps it read-only.

## Funding Gate Purpose

R163 answers whether the local Binance read-only connector environment appears safe enough for later funding review:

- connector mode is present and `read_only`
- API key and secret are present without printing secret values
- Binance live trading and Hammer live execution flags are disabled
- global kill switch remains enabled or conservatively unknown
- the target lane remains `paper`
- balance status is classified without enabling trading

The default minimum estimate is:

```text
minimum_balance_required_estimate_usdt=44
```

This estimate does not authorize execution.

## Read-Only Connector Boundary

R163 reuses:

```text
src/app/hammer_radar/operator/binance_readonly.py
```

That helper is environment/status only. It does not import an exchange SDK, sign requests, create order payloads, or place orders.

R163 reports read-only actions as allowed only for inspection:

- `read_exchange_info`
- `read_account_status` when env presence is complete

R163 explicitly forbids:

- `place_order`
- `cancel_order`
- `transfer`
- `withdraw`
- `enable_live_trading`

## No-Network Default

Preview mode does not require network:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  funding-readonly-precheck \
  --minimum-balance-usdt 44
```

Recording also does not require network:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  funding-readonly-precheck \
  --minimum-balance-usdt 44 \
  --record-precheck \
  --confirm-funding-readonly-precheck "I CONFIRM FUNDING READONLY PRECHECK RECORDING ONLY; NO ORDER; NO BINANCE TRADING CALL."
```

The ledger is:

```text
logs/hammer_radar_forward/funding_readonly_prechecks.ndjson
```

## Balance Gate

R163 does not add new Binance signed request infrastructure. The existing repo has a read-only connector status helper, but no safe reusable balance-read function.

Therefore:

- without `--allow-readonly-network-check`, env-ready status classifies as `READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED`
- with `--allow-readonly-network-check`, R163 reports `READONLY_BALANCE_CHECK_NOT_AVAILABLE` unless a later phase adds or discovers an existing safe read-only balance helper
- no order, test-order, protective order, transfer, or withdrawal endpoint is called

## Secret Safety

R163 prints only presence booleans and a short API key preview. It never prints:

- API secret
- raw API key
- signatures
- auth headers
- `.env` values

The safety object keeps `secrets_shown=false`.

## No Live Execution

R163 keeps:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `protective_payload_created=false`
- `signed_request_created=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `protective_order_endpoint_called=false`
- `transfer_endpoint_called=false`
- `withdraw_endpoint_called=false`
- `env_mutated=false`
- `config_written=false`
- `risk_contract_config_written=false`
- `global_live_flags_changed=false`
- `paper_live_separation_intact=true`

R163 does not change lane modes and does not set any short lane to `tiny_live`.

## Next Possible R164

R164 may run only if an existing connector safely supports a read-only balance check. It must remain optional behind an explicit read-only network flag, must not create signed order material, and must not call order, test-order, protective, transfer, withdrawal, or live-enable endpoints.
