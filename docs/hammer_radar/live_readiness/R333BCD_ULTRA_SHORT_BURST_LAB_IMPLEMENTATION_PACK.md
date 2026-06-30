# R333BCD Ultra Short Burst Lab Implementation Pack

R333BCD implements the first usable paper-only tooling for the `ULTRA_SHORT_LEVERAGE_BURST` family. It combines R333B, R333C, and R333D because all three are read-only diagnostics over the same isolated burst-lab evidence contract.

This is not live trading, not Tiny Live, not standard Strategy Lab promotion, not observed expansion, and not a risk-contract write.

## Components

- R333B backtest adapter: `src/app/hammer_radar/operator/ultra_short_burst_backtest_adapter.py`
- R333C terminal panel: `src/app/hammer_radar/operator/ultra_short_burst_visual_terminal_panel.py`
- R333D risk preview: `src/app/hammer_radar/operator/ultra_short_burst_risk_contract_preview.py`
- R333BCD combined pack: `src/app/hammer_radar/operator/ultra_short_burst_lab_implementation_pack.py`

## Ledgers

- `logs/hammer_radar_forward/ultra_short_burst_backtest_adapter.ndjson`
- `logs/hammer_radar_forward/ultra_short_burst_visual_terminal_panel.ndjson`
- `logs/hammer_radar_forward/ultra_short_burst_risk_contract_preview.ndjson`
- `logs/hammer_radar_forward/ultra_short_burst_lab_implementation_pack.ndjson`

The ledgers are diagnostic and paper-only. Use `--no-write` to suppress ledger writes.

## Backtest Adapter Behavior

The adapter reads existing local signal/evidence surfaces for 4m and 8m candidates. It reuses Strategy Lab source/evidence rows and Hammer Radar signal summaries when present.

Rows include the required strategy family, timeframe, side, lane key, source id/status, timestamp status, entry model, leverage, checkpoint seconds, fee/slippage assumptions, fee drag, slippage drag, gross target fields, net ROE formula, sequence flags, result status, evidence quality, liquidation warning, and safety fields.

If second/tick-level price path is missing, rows are marked:

```text
sequence_known=false
sequence_status=SEQUENCE_UNKNOWN_CANDLE_ONLY_OR_NO_INTRABAR_PATH
```

If only summary evidence exists, rows are `SOURCE_SUMMARY_ONLY`. Formula-only rows are `MODEL_PREVIEW_NOT_TRADE_RESULT`. The adapter does not invent checkpoint prices or synthetic performance.

## Sequence Policy

Candle-only OHLC cannot prove TP/SL ordering inside ultra-short windows. `sequence_unknown` rows cannot be live-ready, cannot promote, and cannot satisfy Tiny Live evidence.

## Gross-Only Forbidden Policy

Gross ROE alone is never readiness. Net ROE must account for fee drag and slippage drag:

```text
fee_drag_roe = fee_pct_round_trip * leverage
estimated_slippage_roe = slippage_pct_round_trip * leverage
net_roe = gross_roe - fee_drag_roe - estimated_slippage_roe
price_move_pct_for_gross_roe = gross_roe_pct / leverage
```

Formula previews are not trade results.

## Liquidation Proximity Warning

150x is marked extreme danger. Any future tiny-burst-live discussion must use microscopic sizing, isolated margin only, sequence-known evidence, and a separate human-reviewed burst risk contract. Cross margin is forbidden.

## Visual Terminal Panel

R333C renders terminal text only. It is not a hosted UI or web app. It includes:

- `PAPER ONLY / LIVE PERMISSION FALSE`
- strategy family isolation
- leverage ladder
- checkpoint timeline
- fee drag warning
- liquidation proximity warning
- sequence_unknown warning
- verdict line
- reason codes

## Risk Contract Preview

R333D emits a preview-only object. It does not mutate `configs/hammer_radar/tiny_live_risk_contracts.json`, does not write a risk contract, and does not grant live permission.

Preview fields include isolated-margin-only, cross-margin-forbidden, microscopic-only future sizing, leverage grid, timeout grid, hard-loss ROE grid, minimum net ROE grid, evidence contract requirement, and R333E anti-fantasy fill gate requirement.

## Evidence Readiness Summary

The combined pack reports:

- rows seen
- replay-ready rows
- replay-pending-intrabar rows
- source-summary-only rows
- model-preview-not-trade-result rows
- sequence-known rows
- sequence-unknown rows
- live permission count
- burst live permission count
- risk-contract written count
- synthetic performance created count
- gross-only ready rows
- sequence-unknown live-ready rows

Live permission, burst live permission, risk contract writes, synthetic performance, gross-only readiness, and sequence-unknown live readiness must remain zero.

## R333E / R333F Path

R333E is the next required phase: Burst Lab Evidence Audit And Anti-Fantasy Fill Gate. It must audit sequence_known, fees, slippage, latency, liquidation proximity, and sample count.

R333F is future-only: Tiny Burst Live Activation Gate, only if R333E and the evidence contract pass. Tiny Live remains separately gated and the first Tiny Live lane stays unchanged.

R333G may refine the terminal operator console after R333E.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable kill switches, mutate arming state, submit, create final commands, change Tiny Live lanes, write promotion events, write risk contracts, mutate observed expansion, mutate configs, mutate env, mutate systemd, start schedulers, send Telegram, or create synthetic performance.

## Commands

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_burst_backtest_adapter --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_burst_visual_terminal_panel --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_burst_risk_contract_preview --log-dir logs/hammer_radar_forward --json --include-150x
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.ultra_short_burst_lab_implementation_pack --log-dir logs/hammer_radar_forward --text
```
