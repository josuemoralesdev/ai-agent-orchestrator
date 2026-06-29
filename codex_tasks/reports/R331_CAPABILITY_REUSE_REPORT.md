# R331 Capability Reuse Report

## Phase Classification

- Primary classification: `EXTENSION OF EXISTING CAPABILITY`
- Secondary classification: `WIRING / INTEGRATION`
- Duplicate risk level: `MEDIUM`
- Reason: R331 closely follows R326/R328/R329 Strategy Lab packet patterns and reuses their local ledgers. The risk is duplicating evidence-adapter logic, so R331 is limited to source-data capture row projection and pending-gap classification.

## Capability Scan

### Existing Docs Checked

- `docs/hammer_radar/live_readiness/R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET.md`
- `docs/hammer_radar/live_readiness/R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK.md`
- `docs/hammer_radar/live_readiness/R326_CANDIDATE_FEED_EXPANSION_FOR_STRATEGY_LAB_VARIANTS.md`
- `docs/hammer_radar/live_readiness/R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET.md`

### Existing Modules Checked

- `src/app/hammer_radar/operator/strategy_lab_adapter_output_batch_execution_packet.py`
- `src/app/hammer_radar/operator/strategy_lab_evidence_adapter_pack.py`
- `src/app/hammer_radar/operator/strategy_lab_candidate_feed_expansion.py`
- `src/app/hammer_radar/operator/strategy_lab_variant_batch_runner.py`
- `src/app/hammer_radar/operator/strategy_lab_preview.py`
- `src/app/hammer_radar/operator/paper_refresh_scheduler.py`
- `src/app/hammer_radar/operator/inspect.py`

### Existing Tests Checked

- `tests/hammer_radar/test_strategy_lab_adapter_output_batch_execution_packet.py`
- `tests/hammer_radar/test_strategy_lab_evidence_adapter_pack.py`
- `tests/hammer_radar/test_strategy_lab_candidate_feed_expansion.py`

### Existing Ledgers Checked

- `logs/hammer_radar_forward/strategy_lab_adapter_output_batch_execution_packet.ndjson`
- `logs/hammer_radar_forward/strategy_lab_evidence_adapter_pack.ndjson`
- `logs/hammer_radar_forward/strategy_lab_candidate_feed_expansion.ndjson`
- `logs/hammer_radar_forward/strategy_lab_variant_batch_runner.ndjson`
- `logs/hammer_radar_forward/strategy_lab_preview.ndjson`
- `logs/hammer_radar_forward/strategy_evidence_registry.ndjson`

## Reuse Findings

### R329 Gap Ranking Reuse

R329 already ranks the R328 source-data gaps and identifies priority capture adapters for exits, MA/WMA anchors, review-ready enrichment, 8m short capture, 13m near-miss repair, betrayal inverse lab-only source chains, and 88m watch durability. R331 consumes R329 status and reproduces the recommended source-data path without recalculating promotion or live eligibility.

### R328 Normalized Row Reuse

R328 already emits normalized evidence rows with lane keys, adapter IDs, dimensions, source-chain metadata, sample counts, win rates, average PnL, blockers, and safety fields. R331 reuses those rows as source inputs and maps them into normalized source-data capture rows. It does not create synthetic performance fields.

### Existing Local Data/Ledger Reuse

R331 reads the latest local R328 and R329 ledgers when present, or builds read-only in-memory packets if missing. The only allowed write is its own output ledger:

```text
logs/hammer_radar_forward/strategy_lab_source_data_capture_adapter.ndjson
```

No scheduler, service, risk-contract, promotion, config, env, observed-expansion, Telegram, Binance, or live-trading mutation is needed.

## Duplicate Risk Report

- Similar existing modules: R326 feed expansion, R328 evidence adapter pack, R329 adapter output batch execution packet.
- Similar existing endpoints: `strategy-lab-candidate-feed-expansion`, `strategy-lab-evidence-adapter-pack`, `strategy-lab-adapter-output-batch-execution-packet`.
- Similar existing CLI commands: R326/R328/R329 module CLIs and print scripts.
- Similar existing scheduler tasks: `paper_refresh_scheduler` exists but is not needed for R331.
- Similar existing docs: R326, R328, and R329 live-readiness docs.
- Risk: `MEDIUM`, because R331 could accidentally duplicate R328 evidence adapter behavior or R329 ranking behavior.
- Mitigation: R331 only creates capture rows/artifacts and pending-gap summaries from existing rows. It does not recalculate eligibility, promote, trade, start services, or mutate live/runtime state.

## Reuse / Extend / Create Decision

- Existing capability reused: R326 lane constants and safety map, R328 normalized evidence rows, R329 gap ranking/source status, existing inspect CLI pattern.
- Existing capability extended: Strategy Lab operator packet family and inspect route.
- New capability created: `strategy_lab_source_data_capture_adapter.py`, R331 docs, R331 print script, R331 tests, and the R331 output ledger contract.
- Why new code was necessary: R328 and R329 identify missing source-data needs, but neither emits the R331 source-data capture row schema or adapter packets required for R332.
- Why this is not duplicating prior work: R331 does not replace evidence adapters or rankings. It projects existing data into source-capture artifacts and marks unavailable inputs pending/lab-only/watch-only.

## Why R331 Does Not Start Schedulers

The requested phase is source-ledger-only. Existing schedulers could collect future paper observations, but starting them would mutate runtime state and violate the phase safety scope. R331 reports `scheduler_required=false` on every row and `scheduler_started=false` in safety fields.

## R332/R330 Feed Path

R331 feeds R332 by producing structured captured/pending source-data rows that can be merged back into R328/R329 adapter rows. R330 remains the later human-reviewed observed expansion gate and can only alter observed expansion after human review. Tiny Live remains separately gated and unchanged.
