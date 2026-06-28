# R325 Strategy Lab Promotion Review Packet

## Why R325 Exists

R324 organized the Strategy Lab surface into batch groups and separated candidates into review-ready, needs-more-samples, watch-only, lab-only, and blocked buckets. R325 turns that read-only batch output into a human-readable promotion review packet.

R325 does not promote strategies, does not write promotion events, does not write risk contracts, does not mutate config, does not mutate arming state, and does not change Tiny Live.

## What R324 Produced

Review-ready for human promotion review:

- `BTCUSDT|44m|short|ladder_382_50_618`
- `BTCUSDT|44m|short|ladder_close_50_618`
- `BTCUSDT|44m|short|ladder_22_44_22`
- `BTCUSDT|55m|long|ladder_close_50_618`
- `BTCUSDT|55m|long|market_close`

Needs more samples:

- `BTCUSDT|13m|long|ladder_close_50_618`
- `BTCUSDT|13m|short|ladder_close_50_618`
- `BTCUSDT|8m|short|ladder_close_50_618`

Watch-only:

- `BTCUSDT|88m|long|ladder_382_50_618`

Lab-only:

- `BETRAYAL_INVERSE_LANES`

## Promotion Versus Live Separation

Promotion review means human review of evidence, observations, and risk-contract presence. It is not live authorization.

Every R325 review-ready candidate keeps:

```text
live_permission=false
tiny_live_eligible_now=false
human_review_required=true
```

The first Tiny Live lane remains:

```text
BTCUSDT|44m|long|ladder_close_50_618
```

## Risk-Contract Separation

R325 reads `configs/hammer_radar/tiny_live_risk_contracts.json` and reports contract presence and validity for review-ready candidates. It does not write the file.

Risk-contract presence is preferred for future review, but it is not sufficient for live. Live still requires separate human approval, real candidate detection, final gate clearance, and no safety blockers.

## Betrayal/Inverse Lab-Only Rule

Betrayal/inverse remains lab-only:

- `lab_only=true`
- `tiny_live_eligible_now=false`
- `standard_55_policy_applies=false`
- preferred win rate is 60%
- minimum sample count is 30, preferred sample count is 50
- average PnL must be positive
- original-vs-inverse comparison is required
- source chain is required
- exact risk mapping is required
- stale shadow outcomes are forbidden

## Recommended R326/R327

Recommended R326:

```text
R326 Candidate Feed Expansion for Strategy Lab Variants
```

R326 should expand evidence capture for anchor, exit, near-miss, and variant candidates.

Recommended R327:

```text
R327 Human-Reviewed Observed Expansion Promotion Gate
```

R327 may later alter observed expansion after human review. It must still not authorize live execution.

## Tiny Live Path

Tiny Live remains separately gated. R325 only identifies possible future review candidates. It does not alter the first live lane and does not create final commands. The Tiny Live path must wait for real candidate detection.

## What Not To Mutate

Do not place orders, call Binance order or test-order endpoints, change leverage or margin, mutate live flags, disable the kill switch, mutate arming state, submit, create a final command, change the first Tiny Live lane, write promotion events, write risk contracts, mutate config, mutate env, mutate systemd, start schedulers, send Telegram, or send real Telegram.

## How To Run

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_promotion_review_packet --log-dir logs/hammer_radar_forward --json
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.strategy_lab_promotion_review_packet --log-dir logs/hammer_radar_forward --text
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward strategy-lab-promotion-review-packet
bash scripts/hammer_print_r325_strategy_lab_promotion_review_packet.sh
```

Output ledger:

```text
logs/hammer_radar_forward/strategy_lab_promotion_review_packet.ndjson
```
