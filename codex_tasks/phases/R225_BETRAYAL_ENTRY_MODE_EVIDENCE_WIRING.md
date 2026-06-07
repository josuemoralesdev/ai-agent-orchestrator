# R225 Betrayal Entry Mode Evidence Wiring

## Purpose

Wire future betrayal emission and capture surfaces so `entry_mode` is explicit at the source instead of inferred later.

## Required Inputs

- R224A betrayal source identity evidence collector output.
- R218 strategy evidence registry.
- R219 registry wiring rules.
- Current betrayal emitter, event tracker, full-spectrum capture, and paper signal ledgers.

## Required Safety

- No config writes.
- No env mutation.
- No Binance/network calls.
- No order/test-order/protective endpoint calls.
- No order payloads.
- No live execution.
- No lane mode changes.
- No risk contract config writes.
- No betrayal, signal-origin, or lane promotion.
- No destructive ledger rewrite.

## Expected Behavior

- Extend future betrayal paper emitters/captures to write explicit `entry_mode` where source data actually contains it.
- Keep candidate labels as context only; do not derive `entry_mode` from common defaults.
- Preserve `paper_only=true`, `live_authorized=false`, and `promotion_allowed=false`.
- Report whether R224A missing-entry-mode rows decrease after new local captures.

## Blocked Conditions

- Source data lacks explicit entry mode.
- Any implementation would write configs or change lane modes.
- Any implementation would call Binance/network or create live/order authority.
