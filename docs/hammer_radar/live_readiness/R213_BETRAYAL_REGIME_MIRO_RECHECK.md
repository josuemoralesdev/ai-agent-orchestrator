# R213 Betrayal Regime + Miro Recheck

R213 adds a paper-only diagnostic recheck for betrayal aggregate candidates:

- `222m aggregate`
- `88m aggregate`
- `55m aggregate` when present

It composes the latest R212 event tracker, R211 paper matrix context, R210 true-inverse refresh, existing Markov regime gate output when present, existing/local Miro Fish quality gate output when available, and local candle archives for `222m`, `88m`, and `55m`.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-regime-miro-recheck
```

Append-only record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-regime-miro-recheck \
  --record-recheck \
  --confirm-betrayal-regime-miro-recheck "I CONFIRM BETRAYAL REGIME MIRO RECHECK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Safety

R213 is audit-only. It cannot write env/config/risk/lane state, cannot call Binance or network, cannot create order payloads, cannot disable the kill switch, cannot promote betrayal, cannot set any lane to `tiny_live`, and cannot authorize live execution.

Regime support and Miro Fish support are separated from:

- true inverse validation
- event tracker readiness
- direction split
- live readiness
- promotion eligibility

Even if a candidate receives supportive regime or Miro context, R213 keeps:

- `live_ready=false`
- `promotion_allowed=false`
- `betrayal_live_authorized=false`
- `betrayal_promoted=false`

## Output

The JSON output includes:

- `input_summary`
- `betrayal_regime_context`
- `betrayal_miro_fish_context`
- `betrayal_regime_miro_candidate_rows`
- `betrayal_regime_miro_gap_report`
- `betrayal_regime_miro_recommendations`
- `regime_miro_status`
- `safety`

The ledger is append-only:

```text
logs/hammer_radar_forward/betrayal_regime_miro_recheck.ndjson
```

## Expected R213 Result

Current betrayal candidates remain paper-only. R212 direction split is still required, so R213 should not matrix-strengthen betrayal beyond context review and should recommend R215 direction split resolution from local paper signals/captures only.
