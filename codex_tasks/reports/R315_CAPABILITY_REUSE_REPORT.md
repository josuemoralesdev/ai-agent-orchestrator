# R315 Capability Reuse Report

## Phase Classification

- Primary classification: EXTENSION OF EXISTING CAPABILITY
- Secondary classification: DIAGNOSTIC / AUDIT
- Duplicate risk level: MEDIUM
- Reason: R315 adds alert-decision previewing over the R314 multi-lane observation health panel and existing Telegram/operator notification patterns, but it must not reuse any send path yet.

## Reusable Health Panel Source

- `src/app/hammer_radar/operator/multi_lane_observation_health_panel.py` already builds a compact read-only health payload with timer status, last tick freshness, primary lane contract/status checks, final live safety, paper refresh health, and locked safety flags.
- `logs/hammer_radar_forward/multi_lane_observation_health_panel.ndjson` confirms the live R314 panel currently reports `MULTI_LANE_OBSERVATION_HEALTH_OK`, recent ticks, timer active/enabled/installed, service exit status `0`, preserved baseline lane, primary observed lanes, secondary watch-only lanes, final live safety locked, and only accepted `eth_paper_outcome` non-critical paper refresh degradation.
- `scripts/hammer_print_r314_multi_lane_observation_health_panel.sh` already gives a compact operator text view and is the script pattern R315 should follow.
- `tests/hammer_radar/test_multi_lane_observation_health_panel.py` already seeds observation records, stubs read-only systemctl checks, verifies no config/arming/systemd/live/Binance mutation, and validates the inspect command.

## Existing Telegram And Reporting Surfaces

- `src/app/hammer_radar/operator/notification_watcher.py` contains the existing readiness alert sender, Telegram config sanitizer, alert records, dedupe checks, and `send_telegram_message`. R315 must not call that sender.
- `src/app/hammer_radar/operator/telegram_operator_bridge.py`, `telegram_polling_worker.py`, and `telegram_approval_challenge.py` support inbound operator commands and approval flows. R315 is outbound-preview only and does not need command handling.
- `src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py`, `tiny_live_autonomous_trigger_loop.py`, and `strategy_promotion_watcher.py` already produce Telegram-compatible visibility-only payloads with send disabled by default. R315 should follow this preview-only pattern.
- `src/app/hammer_radar/operator/inspect.py` already includes `multi-lane-observation-health-panel`, `notification-check`, and `readiness-alerts`; R315 should add a sibling inspect route.

## Duplicate Risks

- Existing `notification_watcher.py` can send Telegram messages. Reusing its send path in R315 would violate the phase.
- Existing candidate alert packets focus on candidate visibility, not multi-lane observation health degradation.
- Existing readiness alerts are signal/trade readiness oriented and not specific to R314 timer/lane/final-safety health.

## Alerting Rules

R315 should alert only when operator attention is needed:

- R314 health status is blocked.
- Observation tick is stale beyond `--max-age-seconds`.
- Timer is not installed, enabled, or active.
- Service last exit status is not `0`.
- Any primary contract is invalid.
- Any primary observation status is not OK.
- Candidate freshness reports a critical status if such a signal appears.
- Final live safety is violated.
- Armed lane differs from the baseline first Tiny Live lane.
- Required safety fields differ from locked values.
- Paper refresh has a critical failure.
- Paper refresh degradation includes failed tasks beyond `eth_paper_outcome`.

Non-alert context:

- R314 health is OK.
- No current candidate is present.
- `FRESH_TRIGGER_WAIT`.
- `PAPER_REFRESH_DEGRADED_NON_CRITICAL` when failed tasks are only `eth_paper_outcome`.
- Normal timer ticks.
- Secondary watch-only lanes.
- Preview-only blocked betrayal/candidate states.

## Rate-Limit And Dedup Preview Strategy

- R315 should compute a stable `dedup_key` from severity, reasons, and affected surface.
- It should inspect only its own append-only preview ledger.
- It should report `would_suppress_duplicate=true` when a matching key exists inside the preview window.
- Critical safety violations should not be suppressed in behavior; they can report `would_repeat_critical=true` for visibility.

## Why R315 Does Not Send Anything

R315 is a preview layer. It must prove alert quality, rule coverage, dedup semantics, and safety flags before any real Telegram send gate exists. Real sending belongs in a later human-reviewed phase with an explicit confirmation phrase and no heartbeat spam.
