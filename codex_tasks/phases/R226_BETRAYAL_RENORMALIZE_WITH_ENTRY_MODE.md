# R226 Betrayal Renormalize With Entry Mode

## Purpose

Rerun betrayal source identity normalization using the R225 entry-mode
propagation contract and evidence rows.

## Required Scope

- Read R225 `betrayal_entry_mode_evidence_wiring.ndjson`.
- Read R224A source identity evidence collector output.
- Read R223 source identity normalizer output.
- Read R218 strategy evidence registry and R219 betrayal registry wiring.
- Produce resolver-ready previews only when every registry-required field exists.
- Keep partial rows blocked and explicitly explain missing fields.

## Safety

- No config writes.
- No env writes.
- No live execution.
- No Binance calls.
- No network calls.
- No order payloads.
- No signed requests.
- No transfers or withdrawals.
- No lane mode mutation.
- No risk contract writes.
- No signal-origin, lane, or betrayal promotion.
- No live authorization.

## Expected Output

Produce a paper-only normalization preview and optional append-only audit record.
Do not append normalized source rows unless a future phase explicitly requests
that exact append behavior with separate confirmation.
