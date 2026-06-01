# R165 Readonly Balance Failure Classifier and Funding Gate Recheck

Phase: R165

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R165 Follows R164

R164 added a safe explicit read-only Binance futures account balance check. After env was loaded and the operator ran:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-check \
  --minimum-balance-usdt 44 \
  --allow-readonly-network-check
```

the safety fields stayed clean, but the read-only balance result failed with `HTTPError`.

R165 turns that failure into a non-networked diagnostic recheck:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-failure-recheck \
  --latest-balance-checks 50
```

## Sanitized Failure Classification

R165 reads recent R164 `readonly_balance_checks.ndjson` rows and classifies sanitized fields only:

- `error_type`
- `http_status`
- `binance_code`
- `binance_message`
- `endpoint_family`

It can classify:

- `HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION`
- `HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE`
- `HTTP_404_OR_ENDPOINT_MISMATCH`
- `FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE`
- `READONLY_BALANCE_ENDPOINT_UNAVAILABLE`
- `NETWORK_OR_BINANCE_TEMPORARY_FAILURE`
- `ERROR_BODY_NOT_AVAILABLE`
- `UNKNOWN_HTTP_ERROR`

## Possible Causes

R165 is designed to help distinguish:

- wrong Binance endpoint
- futures versus spot endpoint mismatch
- API key missing futures/account permission
- API key IP restriction
- timestamp, `recvWindow`, or signature mismatch
- futures account not enabled
- Binance regional or temporary endpoint issue
- previous records missing enough sanitized error detail

## Secret and Signature Safety

R165 does not print or write:

- API secrets
- raw API keys
- auth headers
- full signed URLs
- query strings containing `signature`
- `.env` values

R164 was patched so future read-only `HTTPError` results persist only sanitized status/code/message fields and endpoint family. Signed material remains scoped to `readonly_account_status_only` inside R164 and is not returned by R165.

## Recording

R165 preview writes no record. Recording requires:

```text
I CONFIRM READONLY BALANCE FAILURE RECHECK RECORDING ONLY; NO ORDER; NO BINANCE TRADING CALL.
```

Ledger:

```text
logs/hammer_radar_forward/readonly_balance_failure_rechecks.ndjson
```

Rejected confirmations write no record.

## Safety Boundary

R165 does not:

- call Binance
- call order endpoints
- call test-order endpoints
- create order payloads
- create protective payloads
- create signed trading or order requests
- transfer or withdraw
- enable live trading
- mutate env files
- mutate lane config
- write risk-contract config
- set any lane to `tiny_live`
- start or restart services

## Next Possible R166

R166 should branch from the R165 classification:

- if endpoint mismatch is likely, fix only the read-only endpoint family
- if permission/IP/timestamp is likely, produce an operator key and clock checklist
- if error detail remains unavailable, improve sanitized read-only error capture

R166 must remain non-executing: no live execution, no orders, and no secrets printed.
