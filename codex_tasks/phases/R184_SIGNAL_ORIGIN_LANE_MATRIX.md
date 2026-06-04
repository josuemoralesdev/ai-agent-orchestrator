# R184 Signal Origin Lane Matrix

## Purpose

Combine R181 lane evidence ranking with R183 Keter signal-origin scores to build a paper-only lane x origin matrix.

## Scope

R184 should:

- read R181 multi-lane evidence rankings
- read R182 signal-origin registry/feed summaries
- read R183 Keter origin scores
- build lane x origin rows
- identify best lane/origin pairs for paper tracking
- keep registry-only origins blocked from trade-ready matrix status
- recommend paper evidence collection priorities

## Safety

R184 must not:

- place orders
- call Binance
- create executable payloads
- create signed requests
- write env files
- write config files
- change lane modes
- set any lane `tiny_live`
- write risk-contract config
- promote any signal origin
- authorize live execution

## Expected Command

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  signal-origin-lane-matrix
```

## Expected Output

The output should include:

- lane x origin matrix rows
- best paper-only lane/origin pairs
- registry-only detector blockers
- paper tracking recommendations
- next operator move
- next engineering move
- explicit safety object
