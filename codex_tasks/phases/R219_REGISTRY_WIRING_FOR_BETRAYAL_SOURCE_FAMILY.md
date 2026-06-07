# R219 Registry Wiring For Betrayal Source Family

## Purpose

Wire the R216/R217/R212 betrayal source family to consume `strategy_evidence_registry` for timeframes, entry modes, direction rules, source identity requirements, evidence requirements, and safety defaults.

## Scope

- Extend betrayal source emitter refresh to reference R218 source identity requirements.
- Extend betrayal aggregate decomposition to validate ready rows against R218.
- Extend betrayal event tracker surfaces to preserve source identity and event identity requirements.
- Keep all outputs paper-only.
- Do not create v2 source rows unless local evidence is schema-complete.

## Non-Negotiable Safety

- No config writes.
- No env writes.
- No live execution.
- No Binance/network calls.
- No order/test-order/protective endpoint calls.
- No order payloads or signed requests.
- No live authorization.
- No betrayal promotion.
- No signal-origin or lane promotion.
- No lane `tiny_live` mode changes.

## Suggested Validation

```bash
.venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/strategy_evidence_registry.py \
  src/app/hammer_radar/operator/betrayal_source_emitter_refresh.py \
  src/app/hammer_radar/operator/betrayal_aggregate_decomposition.py \
  src/app/hammer_radar/operator/betrayal_event_tracker.py

PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_strategy_evidence_registry.py \
  tests/hammer_radar/test_betrayal_source_emitter_refresh.py \
  tests/hammer_radar/test_betrayal_aggregate_decomposition.py
```
