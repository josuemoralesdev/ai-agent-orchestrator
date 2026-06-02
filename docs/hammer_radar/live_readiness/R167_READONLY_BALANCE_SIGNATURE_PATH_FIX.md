# R167 Readonly Balance Signature Path Fix

R167 follows the R164 explicit read-only balance check failure where Binance returned HTTP 400 with code `-1022` for `futures_account_readonly`: signature not valid. The operator already corrected the IP allowlist and checked clock/NTP, so this phase narrows the remaining blocker to the signed read-only account request path.

## Scope

R167 fixes only the Binance Futures read-only account/balance signing path used by:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  readonly-balance-check \
  --minimum-balance-usdt 44 \
  --allow-readonly-network-check
```

The default command without `--allow-readonly-network-check` remains a no-network preview.

## Signing Requirement

Binance signed REST endpoints require the HMAC SHA256 signature to be computed over the exact query string before the `signature` field is appended. R167 keeps the helper scoped to read-only account status:

- build deterministic params with `recvWindow` and `timestamp`
- create the query string with `urllib.parse.urlencode` in stable key order
- sign that query string with the API secret
- append `signature` only after signing
- send the same query string that was signed

The signed payload does not include `signature`.

## Timestamp And RecvWindow

The read-only balance path now includes `recvWindow` explicitly. The default is `5000` ms, with an optional CLI override:

```bash
--recv-window-ms 5000
```

This is only for the read-only futures account-status request. It does not create or enable trading request signing.

## Sanitized Diagnostics

When the explicit read-only network path creates a signed account request, the balance-check payload may expose only safe diagnostics:

- `endpoint_family=futures_account_readonly`
- `signed_readonly_request_created=true`
- `signed_request_created_scope=readonly_account_status_only`
- `timestamp_used=true`
- `recv_window_ms=5000`
- `signed_query_param_keys=["recvWindow","timestamp"]`
- `signature_shown=false`
- `signed_url_shown=false`

R167 does not output secrets, signatures, full signed URLs, or raw signed query strings.

## Safety Boundary

R167 does not:

- enable live execution
- place orders
- create executable order payloads
- create protective order payloads
- call Binance order endpoints
- call Binance test-order endpoints
- call protective, transfer, or withdraw endpoints
- mutate env files
- mutate lane config
- mutate risk contract config
- change global live flags
- print secrets, signatures, API secrets, or signed URLs

The only network-capable path remains the existing R164 explicit read-only balance check, and Codex did not run that network smoke.

## R165/R166 Continuity

R165 continues to classify sanitized `-1022` failures as timestamp/recvWindow/signature class. After R167, if `-1022` persists, the operator should also suspect that the API key and secret do not match or are not the intended pair.

## Next Possible R168

R168 should be an operator-run retry and funding sync phase. The operator manually reruns the explicit read-only balance check after R167 is merged, records/classifies the result, and syncs the funding gate/readiness view if the account is funded. R168 must remain non-executing, with no lane changes and no config writes.
