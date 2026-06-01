# R166 Readonly Balance Endpoint Fix or Operator Key Check

Phase: R166

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R166 Follows R165

R164 added an explicit read-only Binance balance check and the operator ran it after loading env. The read-only boundary stayed clean:

- connector mode was `read_only`
- live flags were safe
- the request scope was read-only account status
- no order, test-order, protective, transfer, or withdraw endpoint was called
- no signed trading or order request was created

The result still failed with `READONLY_BALANCE_CHECK_FAILED` and `HTTPError`. R165 could only classify that runtime row as `ERROR_BODY_NOT_AVAILABLE`, which meant the sanitized status/body/code/message were not enough to distinguish endpoint mismatch from key permission, IP restriction, timestamp, account type, Binance availability, or another read-only account issue.

## Sanitized Error Capture

R166 keeps the existing R164 `readonly-balance-check` surface and existing ledger:

```text
logs/hammer_radar_forward/readonly_balance_checks.ndjson
```

Future explicit read-only failures now persist only sanitized diagnostic metadata in `balance_check`:

- `error_type`
- `http_status`
- `binance_code`
- `binance_message`
- `endpoint_family`
- `retryable`
- `troubleshooting_hint`
- `sanitized_error_available`

The sanitizer redacts or drops signed URLs, query strings, signatures, API keys, API secrets, auth headers, and raw headers.

## Classification Mapping

R166 keeps the existing R165 no-network command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-failure-recheck \
  --latest-balance-checks 50
```

The recheck now uses the persisted R164 fields to classify:

- `HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION`
- `HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE`
- `HTTP_404_OR_ENDPOINT_MISMATCH`
- `FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE`
- `READONLY_BALANCE_ENDPOINT_UNAVAILABLE`
- `NETWORK_OR_BINANCE_TEMPORARY_FAILURE`
- `ERROR_BODY_NOT_AVAILABLE`
- `UNKNOWN_HTTP_ERROR`

## Operator Checklist

R165 output now includes `operator_checklist` and classification-specific `operator_actions` covering:

- key permission check
- IP restriction check
- Futures account enabled check
- system clock / recvWindow check
- endpoint family check

The default diagnostic command remains no-network. The explicit read-only network check is still operator-run only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-check \
  --minimum-balance-usdt 44 \
  --allow-readonly-network-check
```

## Safety Boundary

R166 does not:

- place orders
- create executable Binance order payloads
- create protective payloads
- call Binance order endpoints
- call Binance test-order endpoints
- call protective order endpoints
- call transfer or withdraw endpoints
- enable live trading
- mutate env files
- mutate lane config
- mutate risk-contract config
- change global live flags
- set any lane to `tiny_live`
- start or restart services

R166 does not print or write secrets, full API keys, API secrets, signatures, full signed URLs, signed query strings, auth headers, or raw headers.

## Next Possible R167

R167 should be an operator-run retry and funding sync:

- operator manually reruns R164 explicit read-only balance check after R166 is merged
- R165 classifies the new sanitized result
- funding gate is synced with the classification
- no live execution
- no lane changes
- no order, test-order, protective, transfer, or withdraw endpoints
