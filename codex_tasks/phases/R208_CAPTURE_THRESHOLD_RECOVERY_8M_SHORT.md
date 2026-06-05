# R208 Capture Threshold Recovery 8m Short

Recover and monitor the BTCUSDT 8m short fresh capture threshold after R206.

Scope:

- Read R176 capture count sync records.
- Read R157 short paper evidence capture records and heartbeats.
- Focus on `BTCUSDT|8m|short|ladder_close_50_618`.
- Report current fresh capture count against the 10/10 threshold.
- Report watcher recency/staleness and safe local restart/monitoring guidance.
- Keep primary origin context as `hammer_wick_reversal` and secondary paper context as `bearish_engulfing` and `three_black_crows`.
- Produce a paper-only recovery roadmap.

Safety requirements:

- no config writes
- no env mutation
- no live execution
- no Binance/network calls
- no order or test-order calls
- no executable or signed payloads
- no transfer or withdraw calls
- no lane mode changes
- no risk contract writes
- no signal-origin or lane promotion
- no live permission or live authorization

R208 is diagnostic/audit only. It should not fund accounts, arm live flags, disable the kill switch, set any lane to `tiny_live`, or infer live readiness from capture recovery alone.
