# R169 Env Role Split Proposal No Write

R169 proposes unambiguous Binance env role names after R168 showed that legacy `BINANCE_API_KEY` / `BINANCE_API_SECRET` can mix market/read-only and account-read credentials.

## Scope

R169 adds:

- `src/app/hammer_radar/operator/env_role_split_proposal.py`
- `env-role-split-proposal` in the inspect CLI
- append-only proposal ledger `logs/hammer_radar_forward/env_role_split_proposals.ndjson`

This phase is proposal-only. It reads current env files only for hash/length fingerprints and does not write `.env`, role env files, configs, lane modes, or risk contracts.

## Proposed Role Names

Market data/status role:

- `HAMMER_MARKET_BINANCE_API_KEY`
- `HAMMER_MARKET_BINANCE_API_SECRET`

Account-read role:

- `HAMMER_ACCOUNT_READ_BINANCE_API_KEY`
- `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET`

Reserved future live role:

- `HAMMER_LIVE_BINANCE_API_KEY`
- `HAMMER_LIVE_BINANCE_API_SECRET`

Runtime safety flags remain:

- `BINANCE_CONNECTOR_MODE=read_only`
- `BINANCE_LIVE_TRADING_ENABLED=false`
- `HAMMER_BINANCE_LIVE_ENABLED=false`
- `HAMMER_LIVE_EXECUTION_ENABLED=false`
- `HAMMER_ALLOW_LIVE_ORDERS=false`
- `HAMMER_GLOBAL_KILL_SWITCH=true`

## Compatibility Plan

Existing `BINANCE_API_KEY` / `BINANCE_API_SECRET` may remain supported short-term.

- Market data should prefer `HAMMER_MARKET_BINANCE_API_KEY` / `HAMMER_MARKET_BINANCE_API_SECRET` when present.
- Account-balance checks should prefer `HAMMER_ACCOUNT_READ_BINANCE_API_KEY` / `HAMMER_ACCOUNT_READ_BINANCE_API_SECRET` when present and keep connector mode read-only.
- Future live variables must not be used unless a later explicitly approved live phase allows them.
- Any fallback to legacy variables must require the key and secret to come from one consistent source.

## Commands

Preview, no ledger write:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  env-role-split-proposal
```

Rejected write attempt:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  env-role-split-proposal \
  --record-proposal \
  --confirm-env-role-split-proposal "wrong"
```

Record proposal only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  env-role-split-proposal \
  --record-proposal \
  --confirm-env-role-split-proposal "I CONFIRM ENV ROLE SPLIT PROPOSAL RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
```

## Safety Boundary

R169 does not:

- call Binance
- place orders
- create executable order payloads
- call order, test-order, protective, transfer, or withdraw endpoints
- mutate `.env`
- mutate `/home/josue/.config/hammer-radar/*.env`
- mutate config files
- change lane modes
- set the 8m short lane to `tiny_live`
- write risk-contract config
- enable live trading
- disable the kill switch
- print full API keys, API secrets, signatures, signed URLs, or raw env values

## Next Phase

R170 should add a no-write adapter preview that reports the code-level preference order for role-specific variables while preserving legacy fallback. It must not write env files, call Binance, or enable live execution.
