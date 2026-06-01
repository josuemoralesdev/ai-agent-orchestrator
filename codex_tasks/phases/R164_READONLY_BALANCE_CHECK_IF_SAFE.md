# R164 Readonly Balance Check If Safe

## Phase

`R164`

## Branch

`r164-readonly-balance-check-if-safe`

## Phase Classification

- Primary classification: DIAGNOSTIC / AUDIT
- Secondary classification(s): WIRING / INTEGRATION, EXTENSION OF EXISTING CAPABILITY, DUPLICATE RISK
- Duplicate risk level: HIGH

## Reason

R163 can classify local read-only connector env readiness, but it does not implement ad hoc Binance signing or balance retrieval. R164 should only proceed if the repo already has, or a future approved phase has added, a safe read-only balance helper that is strictly separate from trading/order paths.

## Main Objective

Optionally perform a read-only USDT balance check for `BTCUSDT|8m|short|ladder_close_50_618` funding review, only through an existing safe helper and only behind an explicit `--allow-readonly-network-check` flag.

## Capability Scan

Inspect before implementation:

- `src/app/hammer_radar/operator/funding_readonly_precheck.py`
- `src/app/hammer_radar/operator/binance_readonly.py`
- `src/app/hammer_radar/operator/binance_live_status.py`
- `src/app/hammer_radar/execution/binance_futures_connector.py`
- `src/app/hammer_radar/operator/inspect.py`
- `tests/hammer_radar/test_funding_readonly_precheck.py`
- `configs/hammer_radar/lane_controls.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `docs/hammer_radar/live_readiness/R163_FUNDING_READONLY_PRECHECK_AND_BALANCE_GATE.md`

## Hard Safety Boundary

- Do not place orders.
- Do not create executable order payloads.
- Do not create protective order payloads.
- Do not call Binance order endpoints.
- Do not call Binance test-order endpoints.
- Do not call protective order endpoints.
- Do not call transfer or withdrawal endpoints.
- Do not enable live trading.
- Do not disable the kill switch.
- Do not mutate env files.
- Do not mutate lane config.
- Do not mutate risk contract config.
- Do not print secrets, signatures, raw keys, auth headers, or `.env` values.
- Do not create new generic Binance signed request infrastructure.
- Do not create signed trading/order request material.

## Required Gate

R164 must default to no network. Any network balance check must require:

```bash
--allow-readonly-network-check
```

If no existing safe read-only balance helper exists, R164 must report:

```text
READONLY_BALANCE_CHECK_NOT_AVAILABLE
```

and stop.

## Expected Validation

Run focused tests first:

```bash
PYTHONPATH=. .venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/funding_readonly_precheck.py \
  src/app/hammer_radar/operator/inspect.py

PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar/test_funding_readonly_precheck.py
```

Broaden only if R164 touches shared connector or CLI behavior.
