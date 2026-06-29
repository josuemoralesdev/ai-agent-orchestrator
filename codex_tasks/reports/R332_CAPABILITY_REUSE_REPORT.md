# R332 Capability Reuse Report

## Phase Classification

- Primary classification: `WIRING / INTEGRATION`
- Secondary classification: `DIAGNOSTIC / AUDIT`
- Duplicate risk level: `MEDIUM`
- Reason: R332 intentionally overlaps R328 adapter rows, R329 rankings, and R331 capture rows, but creates only a read-only merge view instead of another adapter or performance source.

## Capability Scan

Existing docs checked:

- `docs/hammer_radar/live_readiness/R331_STRATEGY_LAB_SOURCE_DATA_CAPTURE_ADAPTER_IMPLEMENTATION.md`
- `docs/hammer_radar/live_readiness/R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET.md`
- `docs/hammer_radar/live_readiness/R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK.md`
- `docs/hammer_radar/live_readiness/R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS.md`

Existing modules checked:

- `src/app/hammer_radar/operator/strategy_lab_source_data_capture_adapter.py`
- `src/app/hammer_radar/operator/strategy_lab_adapter_output_batch_execution_packet.py`
- `src/app/hammer_radar/operator/strategy_lab_evidence_adapter_pack.py`
- `src/app/hammer_radar/operator/strategy_lab_candidate_feed_expansion.py`
- `src/app/hammer_radar/operator/inspect.py`

Existing tests checked:

- `tests/hammer_radar/test_strategy_lab_source_data_capture_adapter.py`
- `tests/hammer_radar/test_strategy_lab_adapter_output_batch_execution_packet.py`
- `tests/hammer_radar/test_strategy_lab_evidence_adapter_pack.py`
- `tests/hammer_radar/test_strategy_lab_candidate_feed_expansion.py`

Existing endpoints checked:

- Existing operator inspect subcommands for R326, R328, R329, and R331.

Existing CLI commands checked:

- `strategy-lab-candidate-feed-expansion`
- `strategy-lab-evidence-adapter-pack`
- `strategy-lab-adapter-output-batch-execution-packet`
- `strategy-lab-source-data-capture-adapter`

Existing scheduler tasks checked:

- R326/R328/R329/R331 docs and modules confirm no scheduler start is part of the Strategy Lab adapter flow.

Existing logs/ledgers/configs checked:

- `logs/hammer_radar_forward/strategy_lab_source_data_capture_adapter.ndjson`
- `logs/hammer_radar_forward/strategy_lab_adapter_output_batch_execution_packet.ndjson`
- `logs/hammer_radar_forward/strategy_lab_evidence_adapter_pack.ndjson`
- `logs/hammer_radar_forward/strategy_lab_candidate_feed_expansion.ndjson`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`

## Reuse / Extend / Create Decision

Existing capability reused:

- R331 normalized source-data capture rows.
- R328 normalized adapter evidence rows.
- R329 adapter batch status and ranking context.
- Existing local ledgers under `logs/hammer_radar_forward/`.
- Existing safety map from the Strategy Lab candidate feed expansion module, extended locally with R332-only observed-expansion and synthetic-performance flags.

Existing capability extended:

- `src/app/hammer_radar/operator/inspect.py` received a new read-only subcommand: `strategy-lab-captured-source-data-merge`.

New capability created:

- `src/app/hammer_radar/operator/strategy_lab_captured_source_data_merge.py`
- `scripts/hammer_print_r332_strategy_lab_captured_source_data_merge.sh`
- `logs/hammer_radar_forward/strategy_lab_captured_source_data_merge.ndjson` when run without `--no-write`.

Why new code was necessary:

- R328 emits adapter rows, R329 ranks adapter usefulness and gaps, and R331 emits source-data rows, but no existing module provides a coherent merged row view that attaches R331 capture status back to R328 adapter rows.

Why this is not duplicating prior work:

- R332 does not create new adapter rows, new source capture rows, new rankings, synthetic performance, promotion events, risk contracts, observed expansion writes, or scheduler work. It consumes existing packets and emits a merge/audit ledger only.

## Duplicate Risk Report

Similar existing modules:

- `strategy_lab_evidence_adapter_pack.py`
- `strategy_lab_adapter_output_batch_execution_packet.py`
- `strategy_lab_source_data_capture_adapter.py`

Similar existing endpoints:

- Inspect subcommands for R328, R329, and R331.

Similar existing CLI commands:

- R328/R329/R331 module CLIs and print scripts.

Similar existing scheduler tasks:

- None. R332 does not start or define a scheduler.

Similar existing docs:

- R328, R329, and R331 live-readiness docs.

Risk:

- `MEDIUM`, because R332 intentionally merges adjacent packet surfaces and could duplicate adapter/capture logic if implemented incorrectly.

Mitigation:

- R332 imports and consumes existing packet builders/loaders.
- Matching uses exact `source_row_id == row_id` first, then the explicit R328/R331 adapter-family map.
- Pending, lab-only, watch-only, and unmatched rows remain explicit.
- All write counts for promotion, risk contracts, observed expansion, schedulers, live orders, Telegram, and synthetic performance remain zero.

## R333 / R330 Flow

- R332 feeds R333 by producing merged adapter rows with source-data status attached.
- R333 should rank merged evidence after source-data readiness is visible.
- R330 can later alter observed expansion only after human review.
- Tiny Live remains separately gated and unchanged.
