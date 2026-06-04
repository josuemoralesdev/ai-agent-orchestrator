# R185 Three Black Crows Detector Preview

## Phase Classification

Primary: EXTENSION OF EXISTING CAPABILITY

Secondary: DIAGNOSTIC / AUDIT, DUPLICATE RISK

Duplicate risk: MEDIUM

## Purpose

Build a paper-only Three Black Crows detector preview for Hammer Radar signal-origin work.

R184 should have identified `BTCUSDT|8m|short|ladder_close_50_618` + `three_black_crows` as detector-priority but not trade-ready. R185 should preview detector logic and produce auditable local evidence without promoting the origin.

## Required Safety

R185 must not:

- place orders
- call Binance
- call order, test-order, protective, transfer, or withdraw endpoints
- create executable order payloads
- sign read-only or trading requests
- write env files
- mutate config files
- write lane config
- write risk-contract config
- change lane modes
- set any lane `tiny_live`
- promote any signal origin
- authorize live execution

## Expected Work

- Inspect R182 registry and R183 scoring outputs.
- Inspect R184 matrix output.
- Reuse existing candle/feed parsing helpers where available.
- Add a detector preview surface for Three Black Crows.
- Keep all output paper-only and audit-only.
- Add focused tests proving registry-only Three Black Crows does not become trade-ready without detector evidence and that the preview creates no live authority.

## Expected Command Shape

Proposed inspect command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  three-black-crows-detector-preview
```

## Expected Output

The preview should include:

- detector status
- candidate lane
- detected pattern preview rows
- source records checked
- confidence or quality dimensions
- blockers
- recommended next operator move
- recommended next engineering move
- `do_not_run_yet`
- full safety object with no live/config/order mutations
