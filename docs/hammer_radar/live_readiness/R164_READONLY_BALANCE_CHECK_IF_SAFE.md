# R164 Readonly Balance Check If Safe

Phase: R164

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R164 Follows R163

R163 proved the local funding precheck can classify the Binance connector as read-only without using network by default. With operator env loaded, R163 can report `READY_READ_ONLY` while still leaving balance status as `READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED`.

R164 adds the next explicit operator surface:

```text
readonly-balance-check
```

It answers whether a read-only account/balance check may be attempted safely, and if explicitly allowed, classifies available USDT against the default estimate:

```text
minimum_balance_required_estimate_usdt=44
```

## No-Network Default

Preview mode never attempts network:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-check \
  --minimum-balance-usdt 44
```

The default output reports `network_check_requested=false`, `network_check_attempted=false`, and `balance_check_attempted=false`.

## Explicit Read-Only Network Flag

R164 can attempt a read-only Binance futures account status check only when the operator supplies:

```text
--allow-readonly-network-check
```

Before network, R164 requires:

- `BINANCE_CONNECTOR_MODE=read_only`
- `BINANCE_LIVE_TRADING_ENABLED=false`
- Hammer live execution and live-order flags remain disabled
- global kill switch is not disabled
- API key and secret are present, reported only as booleans plus API key preview
- target lane remains `paper`
- read-only status allows `read_account_status`

If any condition is unsafe, R164 blocks before network.

## Balance Classifications

R164 reports one of:

- `BALANCE_NOT_CHECKED`
- `READONLY_NETWORK_NOT_ALLOWED`
- `READONLY_CONNECTOR_MISSING_ENV`
- `READONLY_CONNECTOR_NOT_SAFE`
- `READONLY_BALANCE_CHECK_NOT_AVAILABLE`
- `READONLY_BALANCE_CHECK_FAILED`
- `ACCOUNT_NOT_FUNDED`
- `ACCOUNT_FUNDED_BELOW_MINIMUM`
- `ACCOUNT_FUNDED_READY_FOR_REVIEW`
- `UNKNOWN_NEEDS_MANUAL_REVIEW`

`ACCOUNT_FUNDED_READY_FOR_REVIEW` is still review-only. It points to R165 to sync funding with R158 evidence and R162 contract review.

## Secret Safety

R164 never prints:

- API secret
- raw API key
- signatures
- auth headers
- query strings
- `.env` values

The private signed material is limited to the read-only account status request and is never returned in output or written to the ledger.

## Forbidden Actions

R164 does not:

- place orders
- create executable order payloads
- create protective payloads
- call Binance order endpoints
- call Binance test-order endpoints
- call protective order endpoints
- call transfer or withdraw endpoints
- enable live trading
- mutate env files
- mutate lane config
- write risk-contract config
- disable the global kill switch
- set any lane to `tiny_live`

## Recording

Recording requires the exact phrase:

```text
I CONFIRM READONLY BALANCE CHECK RECORDING ONLY; NO ORDER; NO BINANCE TRADING CALL.
```

Ledger:

```text
logs/hammer_radar_forward/readonly_balance_checks.ndjson
```

Recording does not imply live approval or execution authority.

## Next Possible R165

R165 should combine:

- R164 balance result
- R158 fresh short evidence
- R162 risk-contract apply review

It should decide whether funding remains a blocker while preserving no live execution, no lane changes, and no config writes.
