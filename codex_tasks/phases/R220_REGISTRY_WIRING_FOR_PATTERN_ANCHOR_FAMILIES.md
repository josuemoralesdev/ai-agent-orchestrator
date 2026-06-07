# R220 Registry Wiring For Pattern Anchor Families

## Purpose

Wire pattern, anchor, and full-spectrum harvester surfaces to consume the R218 `strategy_evidence_registry` instead of maintaining independent phase target lists.

## Scope

- Use R218 timeframes for pattern outcome mapping, anchor confluence, and full-spectrum paper harvester audit surfaces.
- Use R218 signal-origin manifests for pattern lane matrix and Keter family review.
- Use R218 anchor manifests for WMA/MA anchor preview and confluence surfaces.
- Use R218 evidence requirements for gap reports and recommendations.
- Keep all outputs paper-only.

## Non-Negotiable Safety

- No config writes.
- No env writes.
- No live execution.
- No Binance/network calls.
- No order/test-order/protective endpoint calls.
- No order payloads or signed requests.
- No live authorization.
- No signal-origin or lane promotion.
- No lane `tiny_live` mode changes.

## Suggested Validation

```bash
.venv/bin/python -m py_compile \
  src/app/hammer_radar/operator/strategy_evidence_registry.py \
  src/app/hammer_radar/operator/pattern_lane_matrix_review.py \
  src/app/hammer_radar/operator/anchor_signal_confluence_matrix.py \
  src/app/hammer_radar/operator/wma_ma_anchor_layer_preview.py

PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_strategy_evidence_registry.py \
  tests/hammer_radar/test_pattern_lane_matrix_review.py \
  tests/hammer_radar/test_anchor_signal_confluence_matrix.py
```
