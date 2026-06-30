# R333BCD Capability Reuse Report

## Phase Classification

- Primary classification: EXTENSION OF EXISTING CAPABILITY
- Secondary classification: WIRING / INTEGRATION
- Duplicate risk level: MEDIUM
- Reason: R333BCD extends the R333A design packet and wires existing Strategy Lab evidence/source rows into an isolated paper-only burst lab. It resembles Strategy Lab adapter output and risk previews, so the implementation keeps separate module names, ledgers, event types, and safety flags.

## Capability Scan

Existing docs checked:

- `docs/hammer_radar/live_readiness/R333A_ULTRA_SHORT_LEVERAGE_BURST_LAB_DESIGN_PACKET.md`
- `docs/hammer_radar/live_readiness/R332_STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_INTO_ADAPTER_ROWS.md`
- `docs/hammer_radar/live_readiness/R331_STRATEGY_LAB_SOURCE_DATA_CAPTURE_ADAPTER_IMPLEMENTATION.md`
- `docs/hammer_radar/live_readiness/R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET.md`
- `docs/hammer_radar/live_readiness/R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK.md`

Existing modules checked:

- `src/app/hammer_radar/operator/ultra_short_leverage_burst_lab_design.py`
- `src/app/hammer_radar/operator/strategy_lab_captured_source_data_merge.py`
- `src/app/hammer_radar/operator/strategy_lab_source_data_capture_adapter.py`
- `src/app/hammer_radar/operator/strategy_lab_adapter_output_batch_execution_packet.py`
- `src/app/hammer_radar/operator/strategy_lab_evidence_adapter_pack.py`
- `src/app/hammer_radar/operator/inspect.py`

Existing tests checked:

- `tests/hammer_radar/test_ultra_short_leverage_burst_lab_design.py`
- `tests/hammer_radar/test_strategy_lab_captured_source_data_merge.py`

Existing endpoints checked:

- Operator inspect commands for R328, R329, R331, R332, and R333A.
- Tiny Live final console safety boundary was not changed.

Existing CLI commands checked:

- `strategy-lab-evidence-adapter-pack`
- `strategy-lab-adapter-output-batch-execution-packet`
- `strategy-lab-source-data-capture-adapter`
- `strategy-lab-captured-source-data-merge`
- `ultra-short-leverage-burst-lab-design`

Existing scheduler tasks checked:

- Multi-lane dry-run observation scheduler surfaces and timer preview/install gate names were checked by file discovery and left untouched.

Existing logs/ledgers/configs checked:

- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- `logs/hammer_radar_forward/ultra_short_leverage_burst_lab_design.ndjson`
- `logs/hammer_radar_forward/strategy_lab_captured_source_data_merge.ndjson`
- `logs/hammer_radar_forward/strategy_lab_source_data_capture_adapter.ndjson`
- `logs/hammer_radar_forward/strategy_lab_adapter_output_batch_execution_packet.ndjson`
- `logs/hammer_radar_forward/strategy_lab_evidence_adapter_pack.ndjson`
- `logs/hammer_radar_forward/multi_lane_dry_run_observation.ndjson`
- `logs/hammer_radar_forward/strategy_promotion_events.ndjson`

## Reuse / Extend / Create Decision

- Existing capability reused: R333A constants and safety design, R332 captured source-data merge, R331 source capture rows, R328 evidence rows, inspect packet pattern, and Strategy Lab safety flags.
- Existing capability extended: the read-only packet/inspect/script pattern is extended for R333B, R333C, R333D, and R333BCD.
- New capability created: isolated ultra-short burst lab adapter, terminal panel, risk preview, and combined pack.
- Why new code was necessary: R333A only defined a design/evidence contract. R333BCD needed executable read-only paper-lab tooling without changing normal Strategy Lab promotion, Tiny Live, observed expansion, or risk-contract write paths.
- Why this is not duplicating prior work: existing Strategy Lab rows are standard policy and adapter evidence surfaces. R333BCD consumes them but emits a separate `ULTRA_SHORT_LEVERAGE_BURST` family with separate ledgers, no promotion event, no risk-contract write, and no live permission.

## Why R333B/R333C/R333D Can Be Combined Safely

The three subphases are read-only consumers of the same evidence contract. R333B creates candidate paper rows, R333C renders those rows as terminal text, and R333D produces a preview-only risk envelope. None of them writes configs, mutates arming state, enables live execution, sends Telegram, starts schedulers, submits orders, or creates final commands.

## Existing Signal/Evidence Surfaces Reused

- Hammer Radar local signal ledger for 4m and 8m signal summaries.
- R332 captured source-data merge rows.
- R331 source-data capture rows through R332.
- R328 normalized evidence rows through R331/R332.
- R333A design constants for leverage, checkpoints, fee/slippage policy, liquidation warning, and Tiny Live separation.

## Data Limitations

- Exact detection timestamps may be missing.
- Second/tick-level price path may be missing.
- Candle-only OHLC cannot prove whether TP or SL happened first inside 22s, 44s, 66s, 88s, 132s, or 176s windows.
- Candle-only or summary-only rows are `sequence_unknown`.
- `sequence_unknown` rows cannot promote to live.
- Formula previews are not trade results.
- Gross-only readiness is forbidden.

## Preview Risk Contract Boundary

The R333D object is a recommendation preview. It does not write `configs/hammer_radar/tiny_live_risk_contracts.json`, does not create a risk-contract ledger write, does not grant live permission, and marks cross margin forbidden with isolated-only future preview language.

## Visual Panel Boundary

The R333C panel is terminal-only text. It is not a hosted UI, web app, operator API exposure, or browser surface. It exists only as CLI output and an optional diagnostic ledger.

## R333E Handoff

R333E should audit sequence-known evidence, fees, slippage, latency, liquidation proximity, and sample count. It must reject candle-only fantasy fills, gross-only readiness, sequence-unknown promotion, and any live discussion before the evidence contract passes.

## Duplicate Risk Report

- Similar existing modules: Strategy Lab evidence adapter, source capture adapter, captured source merge, adapter batch execution packet, and existing risk preview/gate modules.
- Similar existing endpoints: existing Strategy Lab inspect commands and R333A inspect command.
- Similar existing CLI commands: `strategy-lab-*` packet commands and `ultra-short-leverage-burst-lab-design`.
- Similar existing scheduler tasks: multi-lane dry-run observation scheduler is adjacent but not reused or started.
- Similar existing docs: R328-R333A live-readiness docs.
- Risk: MEDIUM because the work resembles Strategy Lab adapter rows and risk previews.
- Mitigation: separate family, separate event types, separate ledgers, explicit `paper_only=true`, explicit `live_permission=false`, explicit no-write/no-mutation safety fields, terminal-only visual output, and preview-only risk object.
