# R212 Betrayal Event Tracker

## Purpose

Define or refresh a deterministic betrayal event tracker that can collect future
schema-complete true-inverse samples for R210/R211 without relying on naive
inverse math or raw capture linkage.

## Required Behavior

- Create stable betrayal event identities for symbol/timeframe/direction/entry
  mode/source timestamp.
- Store declared evaluation windows.
- Require explicit direction, entry, stop, take-profit, and local candle-window
  resolution schema.
- Deduplicate events.
- Keep raw full-spectrum captures as seeds until outcome schema is complete.
- Report unresolved, missing-schema, missing-candle, and timestamp-alignment
  blockers separately.

## Safety

R212 must not write config, mutate env, call Binance/network, create order
payloads, place orders, promote betrayal, promote any signal origin/lane, set
any lane to `tiny_live`, disable the kill switch, or authorize live execution.

## Expected Output

- Paper-only event tracker preview.
- Optional append-only event tracker ledger gated by an exact paper-only
  confirmation phrase.
- Clear handoff back to R210 refresh after enough deterministic samples exist.
