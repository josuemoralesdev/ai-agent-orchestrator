# R198 Full-Spectrum Harvester Expansion

R198 expands paper-only harvest coverage from the R196 full-spectrum coverage audit. It builds a runtime harvest scope for all discovered BTCUSDT `ladder_close_50_618` timeframe/direction lanes, including configured R180 paper lanes and R196 discovered unconfigured gaps.

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  full-spectrum-harvester-expansion \
  --latest-signals 3000 \
  --latest-scans 5000
```

Short bounded smoke loop:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  full-spectrum-harvester-expansion \
  --latest-signals 3000 \
  --latest-scans 5000 \
  --max-iterations 2 \
  --sleep-seconds 1 \
  --iteration-timeout-seconds 30 \
  --heartbeat-every 1 \
  --run-harvester-loop \
  --record-harvest \
  --confirm-full-spectrum-harvest "I CONFIRM FULL SPECTRUM PAPER HARVESTING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Rejected confirmation smoke:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  full-spectrum-harvester-expansion \
  --record-harvest \
  --confirm-full-spectrum-harvest "wrong"
```

Ledgers:

```text
logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson
logs/hammer_radar_forward/full_spectrum_harvester_heartbeats.ndjson
```

The scope separates:

- `configured_paper_lanes`: existing `lane_controls.json` paper lanes, read-only
- `discovered_unconfigured_paper_lanes`: R196/default full-spectrum runtime lanes with `mode=paper_discovered_unconfigured`, `config_write_allowed=false`, and `live_authorized=false`
- `tiny_live_reference_lanes`: existing tiny-live lanes observed as reference only

R198 includes the default expanded BTCUSDT timeframes:

```text
4m, 8m, 13m, 22m, 44m, 55m, 88m, 222m, 444m, 666m, 888m, 4H, 13H, 13D
```

Safety state:

- paper/audit only
- no Binance/network calls
- no env/config/lane/risk-contract writes
- no lane mode changes
- no tiny-live promotion
- no signal-origin promotion
- no order/test-order/protective/transfer/withdraw calls
- no signed requests or executable payloads
- WMA/MA anchor layer is explicitly future-only and cannot authorize live

R198 prepares, but does not implement, a future WMA/MA anchor-layer preview. That work belongs in R199 or later and must start as paper-only context.
