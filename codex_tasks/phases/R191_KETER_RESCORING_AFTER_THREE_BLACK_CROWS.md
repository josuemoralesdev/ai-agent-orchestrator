# R191 Keter Rescoring After Three Black Crows

## Purpose

Rescore Keter signal-origin context after R190 records local Three Black Crows detector feedback.

## Scope

R191 should:

- read `logs/hammer_radar_forward/signal_origin_feedback_sync.ndjson`
- read existing R182 registry context
- read existing R183 Keter scoring context
- incorporate R190 review evidence for `three_black_crows`
- report whether `three_black_crows` can move from detector priority only toward a paper-tracking candidate after review
- recommend whether R184 lane matrix should be rerun after rescoring

## Safety

R191 must not:

- place orders
- call Binance
- call any network
- create executable payloads
- create order payloads
- create signed requests
- write env files
- mutate env values
- write config files
- write registry source definitions
- write lane config
- set any lane `tiny_live`
- write risk-contract config
- promote any signal origin
- promote any lane
- authorize live execution

## Expected Command

Define an R191 inspect command that previews by default and records only after an exact paper-only confirmation phrase.

## Expected Output

The output should include:

- latest R190 feedback summary
- prior Keter context for `three_black_crows`
- paper-only rescoring recommendation
- lane-matrix rerun recommendation
- blockers
- next operator move
- next engineering move
- explicit safety object
