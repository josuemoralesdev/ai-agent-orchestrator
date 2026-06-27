# R315 Multi-Lane Observation Alerting Preview

## Why R315 Exists

R314 built a compact Multi-Lane Observation Health Panel over recurring dry-run observation. R315 adds a preview-only alert decision layer so the operator can see when a future Telegram/operator alert would be useful.

R315 does not send Telegram messages. It does not install timers, mutate systemd, mutate config, mutate arming, change env files, change risk contracts, enable live flags, submit anything, or create final commands.

## Alert Philosophy

No heartbeat spam. No recurring "everything is fine" messages. R315 alerts only when operator attention is needed because a health, timer, lane, paper refresh, or final live safety surface is degraded or unsafe.

## Alert Conditions

- `health_status=MULTI_LANE_OBSERVATION_HEALTH_BLOCKED`
- stale observation tick beyond `--max-age-seconds`
- timer not installed, enabled, or active
- service last exit status is not `0`
- any primary contract invalid
- any primary observation status not OK
- candidate freshness status is critical, when present
- final live safety violation:
  - `real_order_forbidden != true`
  - `submit_allowed != false`
  - `final_command_available != false`
- armed lane differs from the baseline first Tiny Live lane
- required safety flags differ from locked values
- paper refresh critical failure
- paper refresh degradation for tasks beyond `eth_paper_outcome`

## Non-Alert Conditions

- health status OK
- `current_candidate_seen=false`
- `candidate_freshness_status=FRESH_TRIGGER_WAIT`
- `PAPER_REFRESH_DEGRADED_NON_CRITICAL` with failed tasks only `eth_paper_outcome`
- normal timer tick
- no candidate
- secondary watch-only lanes present
- preview-only blocked candidate/betrayal context

## Severity Model

- `INFO_PREVIEW_NO_SEND`: no actionable alert
- `WARNING_PREVIEW_NO_SEND`: degraded but live safety remains locked
- `CRITICAL_PREVIEW_NO_SEND`: blocked health, safety violation, primary lane invalidity, final live safety violation, armed lane mismatch, or critical paper refresh failure

## Dedup And Rate-Limit Preview

R315 computes a stable `dedup_key` from severity, reasons, and affected surface. It reads its own append-only ledger:

```text
logs/hammer_radar_forward/multi_lane_observation_alerting_preview.ndjson
```

If a matching preview exists inside the default 900 second window, R315 reports `would_suppress_duplicate=true` for non-critical alerts. Critical alerts are not suppressed in behavior; repeated critical matches report `would_repeat_critical=true`.

## How To Run

JSON:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_alerting_preview --log-dir logs/hammer_radar_forward --json
```

Text:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_alerting_preview --log-dir logs/hammer_radar_forward --text
```

Inspect route:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward multi-lane-observation-alerting-preview
```

Operator script:

```bash
bash scripts/hammer_print_r315_multi_lane_observation_alerting_preview.sh
```

No write preview:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.multi_lane_observation_alerting_preview --log-dir logs/hammer_radar_forward --json --no-write
```

## Why It Does Not Send Yet

R315 proves rule quality, dedup behavior, message shape, and safety flags first. Real Telegram sending needs a separate human-reviewed send gate, exact confirmation phrase, explicit no-heartbeat policy, and tests proving no alert can imply live authorization.

## Safety Fields

Every R315 output reports the required no-live/no-send fields, including:

- `live_execution_enabled=false`
- `allow_live_orders=false`
- `global_kill_switch=true`
- `order_placed=false`
- `real_order_placed=false`
- `execution_attempted=false`
- `submit_allowed=false`
- `final_command_available=false`
- `real_order_forbidden=true`
- `binance_order_endpoint_called=false`
- `binance_test_order_endpoint_called=false`
- `leverage_change_called=false`
- `margin_change_called=false`
- `secrets_shown=false`
- `paper_live_separation_intact=true`
- `autonomous_arming_state_changed=false`
- `global_live_flags_changed=false`
- `risk_contract_config_mutated=false`
- `config_written=false`
- `env_written=false`
- `env_mutated=false`
- `systemd_unit_mutated=false`
- `scheduler_started=false`
- `telegram_send_called=false`
- `telegram_message_sent=false`

## Recommended R316 Paths

If R315 is clean:

```text
R316 Human-Reviewed Observation Alert Send Gate
```

Add gated real Telegram sending for `alert_required=true` only, with an exact phrase and no heartbeat spam.

If R315 shows blockers:

```text
R316 Alerting Preview Repair
```
