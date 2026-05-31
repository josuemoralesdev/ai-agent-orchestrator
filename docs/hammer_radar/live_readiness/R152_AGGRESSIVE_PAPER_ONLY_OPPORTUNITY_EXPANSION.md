# R152 Aggressive Paper-Only Opportunity Expansion

Phase: R152

Status: IMPLEMENTED

Classification:
- Primary: EXTENSION OF EXISTING CAPABILITY
- Secondary: WIRING / INTEGRATION, DIAGNOSTIC / AUDIT, DUPLICATE RISK
- Duplicate risk level: HIGH

## Why R152 Follows R151

R151 showed the R150 watcher path was healthy but starved for proof on the two narrow target lanes:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|44m|long|ladder_close_50_618`

The source feed was live and the watcher completed its bounded run, but `paper_proof_captured=false`. R151 also showed short candidates and wrong-timeframe candidates existed while target-lane fresh count stayed at zero. Waiting only on two long lanes is too narrow for collecting useful paper proof and opportunity statistics.

R152 expands visibility across BTCUSDT 4m, 8m, 13m, and 44m in both directions for paper observation. It does not expand live execution.

## Paper-Only Boundary

R152 preserves the existing tiny-live intent lanes:

- `BTCUSDT|13m|long|ladder_close_50_618` remains `tiny_live`
- `BTCUSDT|44m|long|ladder_close_50_618` remains `tiny_live`

All newly proposed lanes are `paper` only:

- `BTCUSDT|4m|short|ladder_close_50_618`
- `BTCUSDT|8m|short|ladder_close_50_618`
- `BTCUSDT|13m|short|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`

Existing 4m and 8m long paper lanes are preserved. Shorts are paper-only because this phase is about opportunity distribution and proof discovery, not live short authorization.

## Preview Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  paper-opportunity-expansion \
  --latest-signals 1000 \
  --latest-scans 2000 \
  --include-default-expansion
```

The preview writes no config and no ledger. It reports existing lanes, proposed lanes, lanes to add, lanes to preserve, recent BTCUSDT timeframe/direction distribution, paper watch scope, safety flags, and safe next commands.

## Rejected Apply Check

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  paper-opportunity-expansion \
  --include-default-expansion \
  --apply \
  --confirm-paper-expansion "wrong"
```

This must return `PAPER_OPPORTUNITY_EXPANSION_REJECTED`, `confirmation_valid=false`, and `config_written=false`.

## Confirmed Apply Command

Human operator only, after review and tests:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  paper-opportunity-expansion \
  --include-default-expansion \
  --apply \
  --record-expansion \
  --confirm-paper-expansion "I CONFIRM PAPER OPPORTUNITY EXPANSION ONLY; NO LIVE LANES; NO ORDER; NO BINANCE CALL."
```

Confirmed apply mutates only:

```text
configs/hammer_radar/lane_controls.json
```

The optional ledger is append-only:

```text
logs/hammer_radar_forward/paper_opportunity_expansions.ndjson
```

## Post-Apply Checks

After a human-confirmed apply, check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  lane-control-status
```

Expected:

- 13m long remains `tiny_live`
- 44m long remains `tiny_live`
- all short lanes are `paper`
- all non-target long lanes are `paper`
- no new `tiny_live` lanes exist
- live execution remains disabled
- orders remain disallowed

## No Live Execution

R152 does not:

- place real orders
- create executable order payloads
- create protective payloads
- call Binance order, test-order, protective, account, or private endpoints
- create signed request material
- mutate env files
- mutate global live flags
- disable the kill switch
- bypass R106/global gates
- authorize live shorts
- set any new lane to `tiny_live`

R153 should run the expanded paper watch and opportunity recheck over this paper scope, then identify the strongest next candidate family without changing live authorization.
