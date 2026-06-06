# R212 Betrayal Event Tracker

## Purpose

R212 creates deterministic, paper-only betrayal event identities for future
sample tracking. It links R211 context, R210 true-inverse refresh, R209
integration context, local full-spectrum captures, paper signals, and existing
paper outcomes without treating aggregate context or raw captures as validated
directional proof.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-event-tracker
```

Record append-only tracker preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-event-tracker \
  --record-tracker \
  --confirm-betrayal-event-tracker "I CONFIRM BETRAYAL EVENT TRACKER RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

## Output

- `event_seed_candidates` for `222m aggregate`, `88m aggregate`, and `55m aggregate` when available.
- Deterministic `event_identity` and `event_identity_hash` previews.
- Direction context classification:
  - `aggregate_context_only`
  - `direction_specific`
  - `unknown`
- Gap report for missing direction split, entry mode, timestamp, and outcome window requirements.
- Recommendations for R213 and R214.

## Safety

R212 is paper event tracking only. It cannot write env/config/risk/lane state,
call Binance or network, create order payloads, place orders, disable the kill
switch, promote betrayal, promote signal origins or lanes, create live
authorization, or infer live readiness.

Aggregate-only candidates can seed context tracking, but they are marked
`not_direction_specific` and cannot count as validated directional proof.

Raw full-spectrum captures can seed future tracking only when schema fields are
present. They cannot count as resolved outcomes.

## Ledger

Append-only tracker records are written only after exact confirmation:

`logs/hammer_radar_forward/betrayal_event_tracker.ndjson`

## Next Phases

- R213 should recheck regime and Miro Fish context for betrayal candidates as paper-only evidence.
- R214 should resolve tracked betrayal events into future paper outcomes without config writes, Binance/network calls, or live execution.
