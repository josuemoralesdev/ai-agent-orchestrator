# R179 Risk Contract Config Apply If Ready No Live

## Phase Classification

- Primary: WIRING / INTEGRATION
- Secondary: EXTENSION OF EXISTING CAPABILITY, DIAGNOSTIC / AUDIT
- Duplicate risk: MEDIUM

## Purpose

Apply the `BTCUSDT|8m|short|ladder_close_50_618` risk-contract config only if R178 shows the apply packet is ready and every required gate is satisfied.

## Required Preconditions

- Evidence threshold is met: at least 10 unique fresh captures.
- Funding is ready from local role-specific funding evidence.
- R161 draft exists and still matches the target family.
- R162/R178 future patch preview is sane.
- Operator provides an exact R179 config-apply confirmation.
- Focused tests pass before apply.

## Non-Negotiable Safety

R179 must not:

- Enable live execution.
- Change lane mode.
- Set the short lane `tiny_live`.
- Call Binance.
- Call order, test-order, protective, transfer, or withdraw endpoints.
- Create executable order payloads.
- Sign trading/order requests.
- Print secrets.
- Mutate `.env` files.
- Disable kill switches.

## Expected Behavior

- Preview mode remains default and writes no config.
- Wrong confirmation rejects.
- Correct confirmation may write only the target risk-contract config patch when all gates pass.
- Even after a config write, lane mode remains `paper` and live execution remains disabled.

## Validation Requirements

- `py_compile` changed modules.
- Focused R179 tests.
- Related R161/R162/R177/R178 tests.
- Config diff proves only the intended risk-contract config changes when apply is explicitly confirmed.
- Safety output proves no live execution, no order, no Binance call, and no lane mode change.
