# R156 Short Strategy Packet for BTCUSDT 8m Short

Phase: R156

Status: IMPLEMENTED

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: EXTENSION OF EXISTING CAPABILITY, WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R156 Follows R155

R155 identified the next candidate door as `BTCUSDT|8m|short|ladder_close_50_618`. That recommendation was a short strategy review only. It did not allow a config change, lane promotion, live order, Binance call, or tiny-live authorization.

R156 packages the 8m short family for future review by reusing existing paper evidence, expanded paper watch distribution, promotion candidate audit summaries, and betrayal inverse summaries.

## Short Golden Pocket Interpretation

For short candidates, the golden pocket is interpreted as a resistance/retrace zone, not support.

Short-specific review expectations:

- entry concept: retrace into resistance followed by paper-proven rejection
- invalidation: above the relevant swing high or resistance zone
- take profit: below entry toward downside continuation or prior liquidity
- stop/TP logic must not be copied blindly from long-side support logic

## Evidence Thresholds

Future short review thresholds are:

- minimum paper outcomes: 30
- minimum fresh candidates: 10
- preferred win rate: 52 percent
- average PnL must be positive
- stop dominance must be controlled
- explicit future operator approval required

These thresholds are review criteria only. They do not promote the lane or arm live execution.

## Paper-Only State

The target lane remains `BTCUSDT|8m|short|ladder_close_50_618 mode=paper`.

R156 does not set any lane to `tiny_live`, write lane config, create payloads, sign requests, call Binance, place orders, mutate env/global flags, or disable the kill switch.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-strategy-packet \
  --latest-outcomes 10000 \
  --latest-signals 3000 \
  --latest-betrayal 5000 \
  --latest-watch-records 500
```

Confirmed packet recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  short-strategy-packet \
  --latest-outcomes 10000 \
  --latest-signals 3000 \
  --latest-betrayal 5000 \
  --latest-watch-records 500 \
  --record-packet \
  --confirm-short-strategy-packet "I CONFIRM SHORT STRATEGY PACKET RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
```

Confirmed recording appends only `logs/hammer_radar_forward/short_strategy_packets.ndjson`.

## Blockers To Tiny Live Now

R156 blocks tiny-live promotion unless future evidence and approvals clear:

- enough paper outcomes for the 8m short family
- enough fresh short candidates
- positive average PnL
- acceptable win rate
- controlled stop dominance
- short-specific stop/TP policy review
- explicit future operator approval
- global/protective/live gates in a future authorized phase

## Next Possible Phase

R157 should collect bounded paper-only evidence for the BTCUSDT 8m short lane with a heartbeat/bounded scan loop. It must not change lane mode, call Binance, create payloads, or execute live orders.
