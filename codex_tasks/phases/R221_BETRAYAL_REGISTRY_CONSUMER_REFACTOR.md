# R221 Betrayal Registry Consumer Refactor

## Purpose

Refactor betrayal source emitter, aggregate decomposition, and event tracker surfaces to consume the R218 `strategy_evidence_registry` directly instead of maintaining independent candidate, timeframe, required-field, or safety-default lists.

## Scope

- Use R218 betrayal candidates for betrayal source family target scope.
- Use R218 `betrayal_source_emitter_v2` required fields for source row construction and validation.
- Use R218 entry mode manifest to reject blocked placeholders.
- Use R218 betrayal evidence requirements in gap reports and recommendations.
- Preserve R219 as an audit view for verifying registry-backed consumer behavior.
- Keep all outputs paper-only.

## Non-Negotiable Safety

- No config writes.
- No env writes.
- No live execution.
- No Binance/network calls.
- No order/test-order/protective endpoint calls.
- No order payloads or signed requests.
- No live authorization.
- No betrayal, signal-origin, or lane promotion.
- No lane `tiny_live` mode changes.
- No risk contract config writes.

## Suggested Validation

```bash
.venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/betrayal_source_emitter_refresh.py \
  src/app/hammer_radar/operator/betrayal_aggregate_decomposition.py \
  src/app/hammer_radar/operator/betrayal_event_tracker.py \
  src/app/hammer_radar/operator/registry_wiring_betrayal_source_family.py

PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_betrayal_source_emitter_refresh.py \
  tests/hammer_radar/test_betrayal_aggregate_decomposition.py \
  tests/hammer_radar/test_betrayal_event_tracker.py \
  tests/hammer_radar/test_registry_wiring_betrayal_source_family.py
```
