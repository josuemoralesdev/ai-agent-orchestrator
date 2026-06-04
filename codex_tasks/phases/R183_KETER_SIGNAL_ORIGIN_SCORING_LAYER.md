# R183 Keter Signal Origin Scoring Layer

## Purpose

Build the paper-only Keter signal-origin scoring layer on top of R182.

R183 should score signal origins, not lanes, using local paper evidence only.

## Inputs

Use R182 registry/feed output and local paper ledgers:

- `logs/hammer_radar_forward/signal_origin_registry.ndjson`
- `logs/hammer_radar_forward/signals.ndjson`
- `logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson`
- `logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson`
- paper outcomes and paper execution ledgers if needed

## Score Factors

Score each origin by:

- reversal strength
- confirmation density
- timeframe alignment
- historical paper outcome
- freshness
- conflict with higher timeframe
- continuation vs reversal type
- registry availability
- unknown/unclassified rate

## Safety

R183 must not:

- place orders
- call Binance
- create executable payloads
- create signed requests
- write env files
- write config files
- write lane config
- write risk-contract config
- change lane modes
- set any lane `tiny_live`
- promote any signal origin to live
- authorize live execution

## Expected Output

Add a preview-first operator surface that reports:

- scored origins
- scoring inputs and weights
- paper-only blockers
- unknown-origin gaps
- detector gaps
- recommended next operator move
- recommended next engineering move
- full safety object proving no execution authority

Any optional ledger recording must require an exact paper-only confirmation phrase.
