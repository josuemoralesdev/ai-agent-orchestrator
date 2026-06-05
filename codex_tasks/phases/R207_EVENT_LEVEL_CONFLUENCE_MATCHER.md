# R207 Event-Level Confluence Matcher

Build an event-level matcher between anchor interactions and signal-origin detections.

Scope:

- Read R203 anchor signal confluence matrix records.
- Read R201 anchor outcome deepening evidence.
- Read detector/tag/outcome ledgers for target signal origins.
- Attempt exact timestamp or candle-open/close matching between anchor events and signal-origin detections.
- Preserve summary-level rows when exact timestamps are unavailable.
- Report which rows can move from `summary_level` to `event_level`.

Safety requirements:

- no config writes
- no env mutation
- no live execution
- no Binance/network calls
- no order or test-order calls
- no executable or signed payloads
- no transfer or withdraw calls
- no lane mode changes
- no risk contract writes
- no signal-origin or lane promotion
- no confluence-based live permission
- no position sizing or position permission

R207 is diagnostic/audit only and must not infer live readiness from confluence scores.
