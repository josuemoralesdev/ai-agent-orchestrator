# R218 Strategy Evidence Registry / Source Identity Manifest

R218 adds a central paper-only registry and source-identity manifest for strategy evidence surfaces. It defines the shared scope for timeframes, entry modes, signal origins, betrayal candidates, anchors, direction rules, source identity requirements, evidence requirements, and safety defaults.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  strategy-evidence-registry
```

Append-only record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  strategy-evidence-registry \
  --record-registry \
  --confirm-strategy-evidence-registry "I CONFIRM STRATEGY EVIDENCE REGISTRY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Wrong confirmations return `STRATEGY_EVIDENCE_REGISTRY_REJECTED` and write no ledger row.

## Manifest Scope

The registry includes:

- timeframes: `4m`, `8m`, `13m`, `22m`, `44m`, `55m`, `88m`, `222m`, `444m`, `666m`, `888m`, `4H`, `13H`, `13D`
- entry modes: `ladder_close_50_618`, `ladder_382_50_618`, `ladder_22_44_22`, `market_close`, `fib_618`, `fib_650`, plus blocked placeholders `unknown` and `entry_unknown`
- normal signal origins: hammer, crows, engulfing, soldiers, and exhaustion wick families
- context signal origins: golden pocket rejection, RSI divergence, WMA/MA anchor context, and registry-only retest families
- betrayal candidates: `222m aggregate`, `88m aggregate`, and `55m aggregate_if_available`
- anchors: `SMA200`, `WMA200`, `custom_wma`, and periods `13`, `21`, `34`, `55`, `89`, `144`, `200`, `233`, `377`, `610`, `888`

## Source Identity

R218 centralizes required source fields for:

- normal signal origins
- `betrayal_source_emitter_v2`
- anchor context

The betrayal v2 contract requires `entry_mode`, `original_direction`, `inverse_direction`, `emitted_direction`, `source_identity`, source/emitted signal ids, event identity, event hash, outcome windows, and explicit paper/live/promotion flags.

## Safety

Every registry family defaults to:

- `paper_only=true`
- `live_authorized=false`
- `promotion_allowed=false`
- `config_write_allowed=false`
- `order_allowed=false`
- `binance_network_allowed=false`

R218 cannot call Binance or network, create order payloads, place orders, transfer, withdraw, write env/config/risk/lane/scoring/matrix state, disable the kill switch, set any lane `tiny_live`, promote betrayal or signal origins or lanes, infer tiny-live readiness, or authorize live execution.

The append-only ledger is:

```text
logs/hammer_radar_forward/strategy_evidence_registry.ndjson
```

## Known Gaps

- R217 still shows betrayal aggregate rows missing entry mode/source identity in local evidence.
- Summary-level anchor confluence remains weaker than event-level confluence.
- Capture-count sync remains a separate readiness blocker and cannot be inferred from registry completeness.

## Next Phases

- R219 should wire betrayal source emitter, decomposition, and event tracker surfaces to consume this registry.
- R220 should wire pattern and anchor family surfaces to consume the same registry.
