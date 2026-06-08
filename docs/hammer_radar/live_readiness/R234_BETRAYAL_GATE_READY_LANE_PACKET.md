# R234 Betrayal Gate-Ready Lane Packet

R234 converts preserved betrayal context into a paper-only gate-ready lane packet. It does not promote betrayal, authorize live execution, write configs, mutate lane controls, call Binance/network, or create order payloads.

## Command

Preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-gate-ready-lane-packet
```

Optional append-only recording:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  betrayal-gate-ready-lane-packet \
  --record-packet \
  --confirm-betrayal-gate-ready-lane-packet "I CONFIRM BETRAYAL GATE READY LANE PACKET RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/betrayal_gate_ready_lane_packet.ndjson
```

## Inputs

R234 reads the latest local records from:

- `capture_priority_rebalance.ndjson`
- `betrayal_upstream_emitter_entry_mode_contract.ndjson`
- `betrayal_entry_mode_source_propagation.ndjson`
- `betrayal_direction_completion.ndjson`
- betrayal shadow / true-paper / paper-signal ledgers
- `weekend_paper_fisherman_supervisor.ndjson`
- `capture_count_sync_8m_short.ndjson`

## Safety State

- Betrayal remains paper/shadow only.
- Official tiny-live lane remains `BTCUSDT|8m|short|ladder_close_50_618`.
- Betrayal is not live-authorized.
- Betrayal is not promoted.
- Lane modes and risk contracts are not written.
- Historical ledgers and normalized rows are not rewritten/appended.
- Binance/network/order/transfer/withdraw paths are not called.

## Current Readiness Meaning

R234 may classify betrayal lanes as gate-prepared shadow context when lane identity and blockers are explicit. This is not live readiness. A future normal opening path still requires global gates, explicit operator approval, risk contract, funding, true inverse/paper evidence thresholds, lane-mode workflow, kill-switch policy, and paper/live separation checks.

## Next Phase

R235 should be a lightweight status-only check that keeps focus on the official 8m short 10/10 threshold while also reporting 8m long near-threshold status, fisherman health, and latest betrayal gate-ready packet status.
