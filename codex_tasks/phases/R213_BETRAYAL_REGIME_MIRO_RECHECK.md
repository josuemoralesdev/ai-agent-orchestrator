# R213 Betrayal Regime / Miro Recheck

## Purpose

Recheck R211 betrayal paper matrix candidates against current regime and Miro
Fish quality gates as paper-only context.

## Scope

- Read R211 betrayal paper matrix context.
- Read R210 betrayal true-inverse refresh.
- Read R209 betrayal integration recheck.
- Read existing Markov regime gate evidence when present.
- Read existing Miro Fish quality gate evidence when present.
- Produce paper-only recommendations for `222m aggregate`, `88m aggregate`,
  and `55m aggregate` when supported by refreshed evidence.

## Non-Negotiable Safety

- No Binance calls.
- No network calls.
- No order payloads.
- No order placement.
- No env writes or mutations.
- No config writes.
- No lane mode changes.
- No risk contract writes.
- No registry or scoring config writes.
- No signal origin promotion.
- No lane promotion.
- No betrayal promotion.
- No live authorization.
- No tiny-live readiness inference.
- Keep kill switch behavior intact.

## Expected Output

- Current regime support status for each betrayal candidate.
- Current Miro Fish quality support status for each betrayal candidate.
- Gap report for missing or stale regime/Miro evidence.
- Paper-only next actions.
- Safety object proving no live/config/order/network behavior occurred.

## Suggested Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-regime-miro-recheck
```

## Validation

- Run focused tests for the new R213 module and CLI.
- Run R211, R210, R209, R205, and R203 related tests.
- Confirm env/config/feed diffs remain empty except append-only R213 ledger when
  explicitly recorded.
