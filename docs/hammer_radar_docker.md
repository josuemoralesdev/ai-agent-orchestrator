# Hammer Radar Docker

Hammer Radar can now run as a containerized service without replacing the existing direct Python and systemd workflow.

## Warning

The current systemd-based runtime still exists and should not be removed or replaced in this phase.

## Build

```bash
docker compose -f docker-compose.radar.yml build hammer-radar
```

## Start

Foreground:

```bash
docker compose -f docker-compose.radar.yml up --build
```

Detached:

```bash
docker compose -f docker-compose.radar.yml up -d --build
```

## Stop

```bash
docker compose -f docker-compose.radar.yml down
```

## View Logs

Container logs:

```bash
docker compose -f docker-compose.radar.yml logs -f hammer-radar
```

Persisted NDJSON files:

```bash
ls -lah logs/hammer_radar
tail -n 5 logs/hammer_radar/signals.ndjson
tail -n 5 logs/hammer_radar/outcomes.ndjson
```

## Confirm Persistence

The compose file mounts `./logs` to `/app/logs`, so Hammer Radar writes persist on the host at:

- `logs/hammer_radar/signals.ndjson`
- `logs/hammer_radar/outcomes.ndjson`
- `logs/hammer_radar/positions.ndjson`
- `logs/hammer_radar/position_events.ndjson`

## Paper Execution

Paper execution is paper-only in this phase. There is no live Binance trading, no API key usage, and no real order placement.

- Tradable signals can open deterministic paper positions in `logs/hammer_radar/positions.ndjson`
- Paper lifecycle events are stored in `logs/hammer_radar/position_events.ndjson`

## Inspection Commands

```bash
.venv/bin/python -m src.app.hammer_radar.operator.inspect summary
.venv/bin/python -m src.app.hammer_radar.operator.inspect signals --limit 5
.venv/bin/python -m src.app.hammer_radar.operator.inspect outcomes --limit 5
.venv/bin/python -m src.app.hammer_radar.operator.inspect positions --status open
.venv/bin/python -m src.app.hammer_radar.operator.inspect positions --status closed
.venv/bin/python -m src.app.hammer_radar.operator.inspect events --limit 20
```

## Execution Adapters

Hammer Radar now has an execution adapter boundary under `src/app/hammer_radar/execution/`.

- default mode is `paper`
- supported modes are `paper` and `binance_stub`
- `binance_stub` is only a dry boundary for future integration
- no live Binance trading or real order placement exists in this phase

## Safety Check

```bash
.venv/bin/python -m src.app.hammer_radar.execution.safety check
```

- live trading is still disabled
- future Binance live integration requires a separate approval phase

## Truth Commands

```bash
.venv/bin/python -m src.app.hammer_radar.operator.truth summary
.venv/bin/python -m src.app.hammer_radar.operator.truth top-setups --limit 10
.venv/bin/python -m src.app.hammer_radar.operator.truth weak-setups --limit 10
.venv/bin/python -m src.app.hammer_radar.operator.truth by-entry-mode
.venv/bin/python -m src.app.hammer_radar.operator.truth by-timeframe
.venv/bin/python -m src.app.hammer_radar.operator.truth strategy-eligible
.venv/bin/python -m src.app.hammer_radar.operator.truth tradable-only
```

## Strategy Config

- supported strategy timeframes are `13m`, `55m`, `666m`, `4H`, `13H`, and `13D`
- strategy filtering is controlled by `src/app/hammer_radar/operator/strategy_config.py`
- defaults remain conservative but are not `13m`-only
- paper execution remains enabled by default and live trading is still disabled
