# R243 Tiny-Live Executable Payload Preview

## Intent

Consume the R242 Binance read-only precision / mark-price result and preview the requirements for applying quantity to a future executable payload.

## Boundaries

R243 must remain preview-only:

- no signing
- no Binance order endpoint
- no Binance test-order endpoint
- no private endpoint
- no order placement
- no submit
- no kill switch disable
- no env writes
- no config writes unless a future phase explicitly defines a separate guarded write gate

## Inputs

- latest R242 read-only precision / mark-price result
- latest R240 non-executable order payload artifact
- latest R238 order preflight
- latest R236 lane-arm artifact
- latest R230 risk contract config
- R228 evidence packet

## Expected Output

R243 should preview how the R242 quantity result would satisfy future executable payload requirements while keeping the payload non-submittable and unsigned.

Recommended command shape:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-executable-payload-preview
```
