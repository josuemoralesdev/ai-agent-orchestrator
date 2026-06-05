# R206 Tiny-Live Readiness Gap Recheck

R206 is a read-only readiness audit after the R196-R205 evidence expansion. It composes local ledgers/config only and separates paper evidence strength from operational live-readiness gates.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-readiness-gap-recheck
```

Record after exact confirmation:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  tiny-live-readiness-gap-recheck \
  --record-recheck \
  --confirm-tiny-live-gap-recheck "I CONFIRM TINY LIVE READINESS GAP RECHECK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/tiny_live_readiness_gap_recheck.ndjson
```

## Current Candidate Context

- Primary lane: `BTCUSDT|8m|short|ladder_close_50_618`
- Primary origin: `hammer_wick_reversal`
- Secondary paper origins: `bearish_engulfing`, `three_black_crows`
- Paper-only: true
- Live authorized: false

## Readiness Rule

Evidence can be strong while tiny-live remains blocked. R206 cannot mark tiny-live ready unless all hard gates are clear:

- funding status is funded and available USDT meets the minimum, currently 44 USDT estimate
- selected lane fresh captures meet the 10/10 threshold
- target risk contract exists and is applied for the selected lane
- lane mode is in a future explicit tiny-live review state, not plain paper
- operator approval exists
- live flags are intentionally armed
- kill switch policy allows the future action
- key separation is respected
- final preflight/review packet happens in a later phase

## Expected Honest Distance

After R205, the evidence stack is better: hammer remains strongest, bearish engulfing is a serious paper candidate, and anchor confluence exists at summary level. That does not create live readiness. Remaining hard blockers still include funding, capture threshold if below 10/10, risk contract application, lane mode, operator approval, live flags, and kill-switch policy.

## Safety

R206 never writes env/config, never calls Binance/network, never creates order or signed payloads, never changes lane mode, never writes risk-contract config, never arms live flags, never disables the kill switch, never promotes lanes/origins, and never authorizes live execution.

## Next Phases

- R207: event-level confluence matcher, local-only.
- R208: BTCUSDT 8m short capture threshold recovery/monitoring, local-only.
- Later: funding sync through existing explicitly gated read-only balance evidence, risk-contract apply review, non-executing tiny-live review packet, operator approval, final preflight.
