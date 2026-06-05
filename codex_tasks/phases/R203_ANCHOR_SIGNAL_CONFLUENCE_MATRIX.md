# R203 Anchor Signal Confluence Matrix

## Purpose

Combine paper-only R201 anchor outcome candidates with signal-origin detections, detector-family outcomes, and lane-ranking context into an anchor x signal-origin confluence matrix.

## Scope

- Consume R201 anchor outcome deepening records.
- Consume R202 pattern-family outcome mapping records when available.
- Reuse existing signal-origin registry, Keter scoring, lane-matrix, local candle feed, and detector-family surfaces.
- Rank anchor candidates by timeframe, anchor type, period, interaction, signal origin, sample quality, and confluence resolution.
- Keep summary-level confluence clearly separated from exact event-level confluence.

## Safety

R203 must remain paper-only and diagnostic/audit only.

It must not:

- write env files
- write config files
- write lane controls
- write risk contract config
- mutate registry/scoring/matrix config
- promote signal origins
- promote lanes
- create anchor-based live permission
- create position sizing
- create order or protective payloads
- sign requests
- call Binance or any network
- call order, test-order, transfer, or withdraw endpoints
- disable the kill switch
- enable live execution
- set any lane `tiny_live`
- place orders

## Expected Output

- Anchor x signal-origin confluence rankings.
- Sample-quality and trap warnings preserved from R201.
- Explicit `paper_only=true` and `live_authorized=false` on all candidate rows.
- Next-action guidance for later Keter/matrix scoring research only, with no config writes.
