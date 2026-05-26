# R138 Autonomous Lane Live-Ready Burn-Down

R138 adds a single diagnostic burn-down report for the autonomous lane path from R122-R137 to a future first tiny-live autonomous execution. It ranks remaining blockers, names the source surface for each blocker, provides safe inspect or evidence-recording commands, and reports a conservative probability ladder for the operator.

R138 does not add live execution, does not create Binance order payloads, does not create protective payloads, does not sign requests, does not call Binance, does not mutate env, and does not mutate lane config. It records only an append-only burn-down report when the exact phrase is supplied:

```text
I CONFIRM LIVE READY BURN DOWN RECORDING ONLY; NO ORDER; NO BINANCE CALL.
```

## Why This Exists

R122-R137 created lane controls, fresh routing, lane commands, autonomous paper execution, tiny-live lane gate, autonomy loop and scheduler, paper executor integration, lane authorization, kill-switch rehearsal, adapter boundary review, cockpit visibility, dry authorization, live adapter rehearsal, protective policy review, and protective preview boundary.

Those surfaces are intentionally separate. R138 composes them into one operator burn-down so the next clearing phase can work in the right order without treating any diagnostic result as execution authority.

## CLI

Preview only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  autonomous-lane-live-ready-burn-down \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618"
```

Rejected recording example:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  autonomous-lane-live-ready-burn-down \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-burn-down \
  --confirm-burn-down "wrong"
```

Confirmed recording writes only:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect \
  --log-dir logs/hammer_radar_forward \
  autonomous-lane-live-ready-burn-down \
  --lane-key "BTCUSDT|13m|long|ladder_close_50_618" \
  --record-burn-down \
  --confirm-burn-down "I CONFIRM LIVE READY BURN DOWN RECORDING ONLY; NO ORDER; NO BINANCE CALL."
```

Ledger:

```text
logs/hammer_radar_forward/autonomous_lane_live_ready_burn_downs.ndjson
```

## Blocker Model

Categories:

`EVIDENCE`, `LANE_MODE`, `AUTHORIZATION`, `PAPER_PROOF`, `PROTECTIVE_POLICY`, `PROTECTIVE_PAYLOAD`, `CREDENTIAL_BOUNDARY`, `ADAPTER_BOUNDARY`, `GLOBAL_GATE`, `KILL_SWITCH`, `ENV_FLAGS`, `RISK_CONTRACT`, `FRESH_SIGNAL`, `UI_VISIBILITY`, `UNKNOWN`.

Severity:

`CRITICAL_BLOCKER`, `HIGH_BLOCKER`, `MEDIUM_BLOCKER`, `LOW_BLOCKER`, `INFO`.

Clearing modes:

`operator_evidence_recording`, `lane_command_preview`, `lane_command_apply_future`, `config_env_future_only`, `read_only_recheck`, `future_phase_required`, `cannot_clear_here`.

## Recommended Clearing Order

1. Fresh lane/router check.
2. Record or verify recent autonomous paper proof via R129.
3. Move or request lane toward `tiny_live` via the R124/R130 path.
4. Rerun R126 tiny-live gate.
5. Rerun R131 kill-switch rehearsal.
6. Rerun R132 adapter boundary.
7. Rerun R136/R137 protective policy and preview.
8. Provide credential presence evidence as booleans only.
9. Rerun R102/R106/global preflights.
10. Rerun R134 dry authorization.
11. Future R139/R140 adapter final review.
12. Only later explicit execution authorization.

## Probability Ladder

The probability ladder is a heuristic, not a readiness authority. It reports bounded 0-100 estimates for current state, after paper proof, after tiny-live lane authorization, after protective readiness, after credentials boundary, after global gate readiness, after adapter boundary, and after final dry authorization.

## Operator Command Pack

The command pack contains copy-only safe commands for lane status, router status, paper integration preview and evidence recording template, R130 preview and recording template, R126, R131, R132, R136, R137, R134, R102, and R106.

No R138 command places orders, calls Binance endpoints, signs requests, creates executable payloads, edits env, writes config, starts services, or enables live flags. The R124 lane-mode command is preview-only; actual lane config application is withheld for future explicit authorization.

## Safety State

R138 always reports:

- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `order_payload_created=false`
- `executable_payload_created=false`
- `protective_payload_created=false`
- `signed_request_created=false`
- `network_allowed=false`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `protective_order_endpoint_called=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`
- `env_mutated=false`
- `config_written=false`
- `global_live_flags_changed=false`

## Prepares R139/R140

R139 should consume the R138 ranked blockers and build an operator clearing pack in the exact order. R140 can later review adapter readiness only after R139 evidence has reduced the burn-down. Neither phase should place orders or call Binance unless a future phase explicitly authorizes that exact behavior.
