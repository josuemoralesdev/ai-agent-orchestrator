# R230 Betrayal Upstream Emitter Entry Mode Contract

## Purpose

Modify future betrayal emitter and capture surfaces so new betrayal rows emit
`entry_mode` and `lane_key` explicitly at creation time, using the R218/R219
registry-backed source contract and the R229 source propagation findings.

## Required Inputs

- `src/app/hammer_radar/operator/betrayal_entry_mode_source_propagation.py`
- `logs/hammer_radar_forward/betrayal_entry_mode_source_propagation.ndjson`
- R225 entry-mode evidence contract
- R226 renormalization preview
- R227 direction completion preview
- R218 strategy evidence registry
- R219 betrayal source-family registry wiring

## Required Behavior

- Future betrayal emitter/capture rows must carry explicit `entry_mode` when
  local source evidence supplies a registry-valid entry mode.
- Future betrayal emitter/capture rows must carry explicit `lane_key` only when
  symbol, timeframe, emitted direction, and registry-valid entry mode exist.
- Do not infer `entry_mode` from common defaults, candidate labels, timeframe,
  or aggregate context.
- Do not infer `lane_key` without symbol, timeframe, emitted direction, and
  registry-valid entry mode.
- Keep all rows paper-only with `live_authorized=false` and
  `promotion_allowed=false`.

## Non-Negotiable Safety

R230 must not:

- write env files
- write config, lane, registry, scoring, matrix, or risk-contract config
- append normalized source rows unless a separate guarded append phase owns it
- call Binance or any network
- create order, test-order, protective, signed, executable, transfer, or
  withdraw payloads
- place orders
- change global live flags
- disable the kill switch
- set any lane `tiny_live`
- promote betrayal, signal origins, or lanes
- infer tiny-live readiness
- authorize live execution

## Validation

- Focused tests proving entry mode and lane key are emitted only from explicit
  local evidence.
- Negative tests proving no common-default, candidate-label, timeframe-only, or
  aggregate-context inference.
- Safety tests proving no env/config mutation, no network/Binance calls, no
  order/live/transfer/withdraw actions, and no betrayal promotion.
