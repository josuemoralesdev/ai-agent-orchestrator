# R132 Live Adapter Boundary Final Review

## Phase

R132 Live Adapter Boundary Final Review

## Classification

Primary: DIAGNOSTIC / AUDIT

Secondary: WIRING / INTEGRATION, DUPLICATE RISK

Duplicate risk: HIGH

## Goal

Inspect the live adapter boundary before any future order-payload dry authorization phase. R132 must prove where the live adapter is still non-executing, identify exact gaps, and define the dry authorization structure needed for a later protected tiny-live order payload review.

## Non-Negotiables

- Do not place real orders.
- Do not create executable Binance order payloads.
- Do not call Binance order endpoints.
- Do not send signed requests.
- Do not print secrets.
- Do not mutate env files.
- Do not enable global live execution.
- Do not bypass R106/global gates.
- Do not implement real execution adapter behavior.
- Do not create a live order endpoint.
- Do not install/start systemd services.
- Do not run sudo.
- Do not commit, merge, or tag.

## Required Inspection Surfaces

- `src/app/hammer_radar/execution/binance_futures_connector.py`
- `src/app/hammer_radar/operator/binance_live_status.py`
- `src/app/hammer_radar/operator/live_env_boundary_review.py`
- `src/app/hammer_radar/operator/final_live_preflight.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_tiny_live_lane_execution_gate.py`
- `src/app/hammer_radar/operator/first_tiny_live_autonomous_lane_authorization.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract.py`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- existing tests for live connector, preflight, boundary, R126, R130

## Required Output

Create a review artifact that reports:

- no real orders placed
- no Binance order endpoint calls
- no signed requests
- exact live adapter gaps
- how first order-payload dry authorization should be structured
- protective order requirements
- credential presence only as booleans
- no secrets printed
- global live flags remain unchanged
- env files remain unchanged
- paper/live separation remains intact

## Expected Command

Add a future inspect mode if needed:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  live-adapter-boundary-final-review
```

## Next Phase Relationship

R132 should prepare R134 first tiny-live order payload dry authorization. It must not create that dry authorization payload itself unless R132 explicitly scopes it as a review-only structure with no exchange endpoint, no signed request, and no executable adapter call.
