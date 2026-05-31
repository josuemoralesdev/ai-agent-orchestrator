# R153 Expanded Paper Watch And Opportunity Recheck

Phase: R153

Status: IMPLEMENTED

Classification:
- Primary: WIRING / INTEGRATION
- Secondary: DIAGNOSTIC / AUDIT, EXTENSION OF EXISTING CAPABILITY
- Duplicate risk level: HIGH

## Why R153 Follows R152

R151 proved the bounded fresh-candidate watcher was healthy but too narrow for the active market: the source feed was live, short and wrong-timeframe signals appeared, and the two target tiny-live lanes did not receive fresh proof.

R152 expanded BTCUSDT paper visibility while preserving tiny-live intent:

- `BTCUSDT|13m|long|ladder_close_50_618` remains `tiny_live`
- `BTCUSDT|44m|long|ladder_close_50_618` remains `tiny_live`
- 4m/8m long lanes remain `paper`
- 4m/8m/13m/44m short lanes are `paper`

R153 makes that expanded paper state observable. It checks current lane config, scans recent local signal and paper-scan ledgers, summarizes fresh/stale paper candidates by lane family, and optionally records the watch result to an append-only local ledger.

## How The Expanded Paper Watch Works

Command:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  expanded-paper-watch \
  --latest-signals 1000 \
  --latest-scans 2000 \
  --all-paper-lanes \
  --include-tiny-live-targets-as-observed
```

The preview writes no ledger and no config. It reports:

- expanded paper lanes
- tiny-live lanes observed but not changed
- lane config mode state
- recent candidate distribution by timeframe and direction
- fresh and stale candidate counts by paper lane
- best next paper lane family for future R154 audit consideration
- safe follow-up commands only

## Recording Evidence

Rejected confirmation check:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  expanded-paper-watch \
  --all-paper-lanes \
  --record-watch \
  --confirm-expanded-paper-watch "wrong"
```

Confirmed record:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  expanded-paper-watch \
  --latest-signals 1000 \
  --latest-scans 2000 \
  --all-paper-lanes \
  --include-tiny-live-targets-as-observed \
  --record-watch \
  --confirm-expanded-paper-watch "I CONFIRM EXPANDED PAPER WATCH RECORDING ONLY; NO LIVE LANES; NO ORDER; NO BINANCE CALL."
```

Confirmed recording appends only:

```text
logs/hammer_radar_forward/expanded_paper_watch.ndjson
```

## Tiny-Live And Short-Lane Boundaries

R153 does not change lane modes. Tiny-live lanes are included only as observed context so operators can confirm they remain unchanged.

Short lanes are paper-only in R153. A short paper candidate can be counted as fresh evidence, but it cannot become live authorization and cannot promote itself to `tiny_live`.

## No Live Execution

R153 does not:

- place real orders
- create executable Binance order payloads
- create protective order payloads
- call Binance order, test-order, protective, account, or private endpoints
- create signed request material
- mutate env files
- mutate lane config
- mutate global live flags
- disable the kill switch
- bypass R106/global gates
- set any new lane to `tiny_live`
- set any short lane to `tiny_live`

## Next Phase

R154 should consume R153 expanded paper watch records and recent outcome stats to identify which lane families deserve future tiny-live consideration. R154 must remain audit-only unless a later phase explicitly authorizes a lane mode promotion.
