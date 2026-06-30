# Hammer Discovery

## Classification

Primary classification: `DIAGNOSTIC / AUDIT`

Secondary classifications: `WIRING / INTEGRATION`, `DUPLICATE RISK`

Duplicate risk level: `MEDIUM`

Reason: this phase creates a runtime self-description from existing Hammer capabilities. It does not add behavior. Duplicate risk is medium because Hammer already has many phase docs, capability indexes, readiness summaries, and operator reports. The new artifacts are justified as a focused cross-cutting extraction rather than another runtime surface.

## Capability Scan

Existing docs checked:

- `README.md`
- `codex_tasks/CODEX_RULES.md`
- `codex_tasks/phases/R334_HAMMER_RUNTIME_SELF_EXTRACTION.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`
- `docs/hammer_radar/R79_FINAL_PROTECTED_LIVE_GATE_REVIEW.md`
- `docs/hammer_radar/R85_EXACT_OPERATOR_APPROVAL_NON_EXECUTABLE_TICKET_BUILDER.md`
- `docs/hammer_radar/R87_LIVE_ENV_TOGGLE_DESIGN_EXECUTION_BOUNDARY_REVIEW.md`
- representative R8x/R9x readiness, source-chain, betrayal, and live-arming docs discovered by search

Existing modules checked:

- `src/app/hammer_radar/main.py`
- `src/app/hammer_radar/signal_engine.py`
- `src/app/hammer_radar/execution/safety.py`
- `src/app/hammer_radar/execution/paper.py`
- `src/app/hammer_radar/execution/base.py`
- `src/app/hammer_radar/execution/binance_futures_connector.py`
- `src/app/hammer_radar/operator/archive.py`
- `src/app/hammer_radar/operator/models.py`
- `src/app/hammer_radar/operator/gate.py`
- `src/app/hammer_radar/operator/readiness.py`
- `src/app/hammer_radar/operator/live_safety.py`
- `src/app/hammer_radar/operator/trade_ticket.py`
- `src/app/hammer_radar/operator/final_approval_intent.py`
- `src/app/hammer_radar/operator/final_live_preflight.py`
- `src/app/hammer_radar/operator/first_live_activation_gate.py`
- `src/app/hammer_radar/operator/first_live_execution_gate.py`
- `src/app/hammer_radar/operator/lane_control.py`
- `src/app/hammer_radar/operator/lane_control_cockpit.py`
- `src/app/hammer_radar/operator/tiny_live_strategy_lane_selection.py`
- `src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py`
- `src/app/hammer_radar/operator/approval_api.py`
- `src/app/hammer_radar/operator/inspect.py`

Existing tests checked:

- `tests/hammer_radar/` file inventory
- endpoint, signal, execution safety, live gate, lane, risk contract, paper, Telegram, and strategy-performance test names discovered by `rg --files`

Existing endpoints checked:

- Approval API route inventory from `src/app/hammer_radar/operator/approval_api.py`
- groups for readiness, trade tickets, paper executions, live safety, live arming, Binance live, strategy performance, Telegram, operator actions, tiny-live controls, and lane cockpit

Existing CLI commands checked:

- `src/app/hammer_radar/operator/inspect.py` parser inventory
- `src/app/hammer_radar/execution/safety.py check`
- docs examples for inspect commands such as `tiny-live-ticket`, `live-arming-preflight`, `readiness-snapshot`, `human-confirmations`, and `final-review-packet`

Existing scheduler tasks checked:

- capability index references to paper refresh scheduler, betrayal tasks, Markov/Miro Fish gates, readiness snapshot, tiny-live ticket builder, and source-chain tasks

Existing logs/ledgers/configs checked:

- `configs/hammer_radar/lane_controls.json`
- `configs/hammer_radar/tiny_live_risk_contracts.json`
- `configs/hammer_radar/autonomous_arming_state.json`
- `configs/hammer_radar/first_live_execution_design_checklist.json`
- log names referenced in code and docs, including signals, outcomes, paper executions, live attempts, human confirmations, tickets, packets, readiness reports, candle archives, and strategy records

## Reuse / Extend / Create Decision

Existing capability reused:

- Hammer docs, capability index, signal engine, operator memory, readiness, gates, lane controls, risk contracts, paper execution, live safety, Approval API, and inspect CLI.

Existing capability extended:

- None at runtime. This phase only adds extraction documents.

New capability created:

- Static runtime extraction artifacts under `runtime_extraction/`.

Why new code was necessary:

- No runtime code was necessary.

Why new documents were necessary:

- Existing docs are phase-specific. R334 asks for a subsystem-level self-description and contract using Hammer vocabulary.

Why this is not duplicating prior work:

- The artifacts summarize the runtime model across existing Hammer capabilities without adding endpoints, commands, schedulers, ledgers, or execution behavior.

## Fundamental Hammer Concepts

- Signal Engine
- candle observation
- hammer and shooting-star detection
- RSI and divergence
- Fibonacci levels and invalidation
- higher-timeframe bias
- strategy evidence
- candidate gating
- lane key
- paper execution
- tiny-live readiness
- risk contract
- approval gate
- execution gate
- final preflight
- kill switch
- paper/live separation
- operator exact phrase
- hash-chain review
- append-only memory

## Operator Concepts

- local Approval API
- inspect CLI
- Telegram operator bridge
- tickets
- review packets
- approval intent
- human confirmations
- final approval intent
- manual outcomes
- paper-only choice
- dry-run lane arming
- final console
- operator next required action

## Safety Concepts

- `live_execution_enabled=false`
- `allow_live_orders=false`
- `global_kill_switch=true`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `secrets_shown=false`
- dry-run/no-write defaults
- no order payload until explicit gate
- no Binance order endpoint until explicit gate
- protective orders required
- stale candidate protection
- exact hash and phrase matching
- daily trade and loss stops

## Memory Concepts

- signal archive
- outcome archive
- paper position ledger
- paper execution ledger
- manual outcome ledger
- candle archive
- risk contract config
- lane control config
- ticket ledgers
- human confirmation ledger
- approval intent ledger
- live attempt ledger
- readiness snapshots
- strategy performance and promotion evidence

## Concepts That Seem Unique To Hammer

- hammer-strength-driven signal identity
- Hammer timeframes such as 4m, 8m, 13m, 22m, 44m, 55m, 88m, 222m, 444m, 666m, 888m
- ladder entry modes such as `ladder_close_50_618`
- exact lane key as strategy and execution identity
- tiny-live risk contract language
- final protected live gate review
- betrayal paper/true-inverse tracking
- Miro Fish and Markov gate support in readiness
- dry-run lane arming as operator intent
- repeated no-order safety fields on operator artifacts

## Concepts That Seem Universal

- observation
- memory
- prioritization
- risk limits
- operator authority
- approval versus execution
- external reality versus local record
- feedback from outcomes
- safety gates
- audit trail
- kill switch
- dry-run before live action

## Concepts That Surprised Me

- Hammer has many forms of approval, but most are intentionally weaker than execution authority.
- The same safety facts are repeated across many artifacts, which appears deliberate rather than accidental.
- Lane controls can say `tiny_live` while still being blocked by global gates and the kill switch.
- Strategy evidence, source-chain health, Markov support, and Miro Fish support all feed readiness, but none of them independently grants execution authority.
- Risk contract interpretation explicitly rejects hidden leverage expansion.

## Concepts That Appear Fundamental

- Signals are observations, not orders.
- Paper execution is real local memory, not live market action.
- Operator review is necessary but not sufficient for live execution.
- Exact hashes and exact phrases bind human intent to the candidate and risk contract.
- Lanes are the unit where strategy, risk, freshness, and operator intent meet.
- Kill switches and live-disabled flags remain authoritative until an explicit future phase changes them.
- External reality is split between market observation, local recorded truth, and guarded exchange execution reality.
