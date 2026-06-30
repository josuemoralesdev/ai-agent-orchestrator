# Hammer Runtime Self Description

## What Hammer Is

Hammer Radar is a trading research, paper execution, live-readiness, and operator-safety subsystem. Its runtime watches market candles, extracts hammer and related strategy signals, scores whether those signals are candidates, remembers outcomes, and presents operator review surfaces for paper and tiny-live workflows.

Hammer is not a generic orchestrator. It is a machine-led, human-approved trading radar with explicit boundaries around real exchange execution.

## What Hammer Knows

Hammer knows its configured trading universe, strategy policies, lane policy, paper/live separation rules, and local memory. Its core runtime knowledge includes:

- BTCUSDT-focused signal records with symbol, timeframe, direction, candle timestamp, hammer strength, Fibonacci levels, invalidation, RSI state, divergence, higher-timeframe bias, trend metadata, and candidate status.
- Strategy configuration for enabled timeframes, minimum hammer strength, bias alignment, entry modes, paper execution, and exit rules.
- Lane controls that classify exact lane keys such as `BTCUSDT|44m|long|ladder_close_50_618` into disabled, paper, armed dry-run, or tiny-live modes.
- Tiny-live risk contracts with notional caps, leverage caps, max loss, protective order requirements, lane identity, and live-disabled fields.
- Operator records, tickets, review packets, approval intent, human confirmations, manual outcomes, paper executions, and live-readiness ledgers.
- Safety constants that keep live execution disabled unless future explicit gates say otherwise.

## What Hammer Observes

Hammer observes external market reality through candle streams and local captured candle archives. The main runtime loop reads Binance Futures BTCUSDT market data through `MarketReader`, resamples it across Hammer timeframes, and captures resampled frames to local archives.

Hammer also observes its own local reality:

- append-only signal and outcome ledgers
- open and closed paper positions
- manual outcome records
- lane control config
- tiny-live risk contract config
- review packets and hash-chain records
- readiness, live-safety, and final-preflight surfaces
- notification and Telegram operator command records

## How Hammer Prioritizes

Hammer prioritizes by converting raw observations into gated candidates:

1. Signal extraction: hammer or shooting-star candle shape, hammer strength, Fibonacci levels, RSI, divergence, and higher-timeframe bias.
2. Candidate gating: enabled timeframe, minimum strength, bias alignment, and no too-recent same-direction duplicate.
3. Strategy evidence: win rate, sample count, average PnL, live eligibility, Markov/Miro Fish support, and source-chain health.
4. Lane policy: exact lane key, lane mode, freshness window, risk limits, protective-order requirement, and global gate status.
5. Readiness class: fresh candidate, risk contract validity, paper/live separation, human review records, dry-run validity, kill-switch posture, and exchange boundary state.

Hammer does not treat a high-score signal as authority to trade live. A signal becomes a candidate, a candidate may become a review ticket, a ticket may be reviewed by an operator, and live execution still remains blocked unless separate execution gates pass.

## How Hammer Preserves Operator Authority

Hammer preserves operator authority by separating machine preparation from human permission.

Machine surfaces can prepare candidates, tickets, review packets, dry-run payload previews, readiness snapshots, and alerts. Operator surfaces record explicit choices such as watch, reject, paper-only, manual-live intent, exact approval phrases, final approval intent, dry-run lane arming, and manual outcomes.

The important boundary is that operator review records are not automatically live execution authority. Exact phrases bind to candidate ids, risk hashes, and packet hashes, but they still flow through live safety, final preflight, activation, and execution gates.

## Where External Reality Is

External market reality enters Hammer through Binance Futures market data and, in authorized read-only paths, exchange metadata such as precision, mark price, credential-presence booleans, and connector status. Hammer stores observed candle reality in local candle archives and stores decision reality in append-only local ledgers.

Real exchange execution reality is intentionally outside Hammer's default runtime. Live order endpoints, account funding, balance checks, signed requests, and real order placement are behind explicit future/live gates and default-blocked connector settings.

## What Hammer Remembers

Hammer remembers through local files, mostly append-only NDJSON and JSON:

- `signals.ndjson`
- `outcomes.ndjson`
- paper position and paper execution ledgers
- manual outcomes
- trade tickets and tiny-live tickets
- live attempts and connector attempts
- human confirmation records
- final approval intents
- readiness snapshots and review packets
- strategy promotion and strategy evidence records
- lane and autonomous arming config
- tiny-live risk contract config
- candle archives

This memory is used to avoid duplicate signals, evaluate outcomes, summarize strategy truth, qualify lanes, enforce daily stops, validate hash chains, and explain blockers.

## Execution Boundaries

Hammer's ordinary execution boundary is paper-only. The default execution adapter creates local paper positions and closes local paper positions. The live connector stub records rejected live attempts and never places orders.

Live-capable code paths are gated by:

- live execution flags
- allow-live-order flags
- global kill switch
- exact operator approval
- risk contract validation
- final review packet and hash matching
- human confirmation records
- paper execution proof
- dry-run validation
- protective order readiness
- Binance credential presence checks without exposing secrets
- explicit future execution gates

## Safety Boundaries

Hammer's safety boundary is conservative by default:

- live execution disabled
- global kill switch active
- live orders disabled
- order placement false
- real order placement false
- execution attempted false unless explicitly rehearsed as safe metadata
- secrets hidden
- no Binance order endpoint calls without explicit approved gate
- paper/live separation intact
- operator API intended for local/private operation
- raw vague commands blocked by Telegram/operator command parsing
- exact confirmation phrases required for high-risk review records

Hammer's safety model treats readiness as evidence, not permission.
