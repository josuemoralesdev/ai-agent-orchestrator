# R138.5 Burn-Down Command Pack Sanity Check

R138.5 adds a compact sanity check over the R138 autonomous lane live-ready burn-down command pack. It reuses the R138 builder, scans the returned safe copy commands for dangerous terms, and reports the next three safe operator actions.

This phase is diagnostic only. It does not place orders, call Binance, create order payloads, create signed requests, mutate env, mutate config, restart services, or record ledgers.

## CLI

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  burn-down-command-pack-sanity \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

Compact view:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  burn-down-command-pack-sanity \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  | jq '.status, .unsafe_command_count, .next_three_safe_actions, .safety'
```

## Output

The command returns:

- `status`: `COMMAND_PACK_SAFE` or `COMMAND_PACK_UNSAFE`
- `lane_key`
- `unsafe_command_count`
- `unsafe_findings`
- `next_three_safe_actions`
- `safety`

Safety flags remain false:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `signed_request_created=false`
- `network_allowed=false`
- `secrets_shown=false`
- `env_mutated=false`
- `config_written=false`

## Reuse Boundary

R138 remains the source for blocker ranking, dependency chain, and command pack creation. R138.5 only validates the commands and summarizes the safest next three actions; it does not become a readiness authority and does not clear blockers.
