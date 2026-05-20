# R101 Live Readiness Index

Phase: R101

Classification:
- Primary: DIAGNOSTIC / AUDIT
- Secondary: WIRING / INTEGRATION, DUPLICATE RISK
- Duplicate risk level: HIGH

Purpose: provide one repo-grounded index of existing Hammer Radar live-readiness surfaces and the exact blockers that remain before tiny-live can be armed. This is a review document only. It does not enable live trading, change env flags, place orders, wire Telegram approval to execution, or create a second readiness source of truth.

## 1. Executive Status

Tiny-live status: BLOCKED.

Exact blockers found from current code/config/docs and local no-network builders:
- Missing R85 tiny-live ticket review approval record: `R85_TINY_LIVE_TICKET_REVIEW_APPROVAL`.
- Missing R86 manual funding and env checklist record: `R86_MANUAL_FUNDING_AND_ENV_CHECKLIST`.
- Missing R88 final human review approval record: `R88_FINAL_HUMAN_REVIEW_APPROVAL`.
- R84 preflight primary blocker: `missing_operator_approval`.
- R87 boundary status: `LIVE_ENV_ARMING_NOT_ALLOWED_YET`.
- R87 boundary blockers: `LIVE_ENV_BLOCKED_BY_EXECUTION_BOUNDARY`, `LIVE_ENV_BLOCKED_BY_NO_REAL_BALANCE_CHECK`, `LIVE_ENV_BLOCKED_BY_MISSING_OPERATOR_APPROVAL`, `ticket_operator_approval_not_recorded`, `LIVE_ENV_BLOCKED_BY_MISSING_CHECKLIST`.
- Connector mode is `DRY_RUN_ONLY`.
- Binance live status is `BLOCKED`: live execution disabled by application default, global kill switch active, live order placement not implemented, `BINANCE_API_KEY` missing, `BINANCE_API_SECRET` missing.
- Live env file was not loaded and `/home/josue/.config/hammer-radar/binance-live.env` was not confirmed present by the static status builder.
- Live execution flag is false.
- Live order allowed flag is false.
- Global kill switch is true.
- Signing is unavailable because API secret is absent from the current process env.
- Live order adapter is not configured.
- Protective orders are not ready: `HAMMER_PROTECTIVE_ORDERS_ENABLED` is false and protective order mode is `PREVIEW_ONLY`.
- Protective stop/take-profit support is reported false in connector status.
- Real account balance/funding check has not been performed; local risk config explicitly says account balance is not checked.
- R90 readiness snapshot remains review-only and non-executable: `ARMING_SNAPSHOT_REVIEW_ONLY`, `ARMING_SNAPSHOT_BLOCKED_BY_MISSING_REVIEW_RECORDS`, `ARMING_SNAPSHOT_BLOCKED_BY_LIVE_ENV_BOUNDARY`, `ARMING_SNAPSHOT_NON_EXECUTABLE_ONLY`.

Non-blockers currently confirmed:
- Current risk contract hash is present and hash-chain-consistent in R90 output.
- Current packet hash is present and hash-chain-consistent in R90 output.
- R83 Miro Fish currently reports support for `normal|BTCUSDT|13m|long|ladder_close_50_618`.
- Source-chain warnings were not present in the R90 local builder output.

## 2. Current Architecture Map

Scanner layer:
- Source modules include `market_reader.py`, `signal_engine.py`, `multi_symbol_scanner.py`, and market-intelligence surfaces.
- Primary local ledgers include `signals.ndjson`, `outcomes.ndjson`, `positions.ndjson`, `position_events.ndjson`, and paper-refresh run records.

Strategy layer:
- Hammer/R9 signal logic, timeframe policy, entry-mode analysis, Miro Fish quality gate, Markov regime gate, betrayal audit, and candidate revalidation live under `src/app/hammer_radar/operator/`.
- R82/R83/R92/R94 docs describe regime, Miro Fish, and strategy-performance context.

Paper execution layer:
- `paper_execution.py`, `trade_ticket.py`, `positions.py`, and approval API paper endpoints record paper-only tickets and executions.
- `paper_executions.ndjson`, `trade_tickets.ndjson`, `positions.ndjson`, and `position_events.ndjson` are paper/audit ledgers, not live execution permission.

Performance/promotion layer:
- `strategy_performance.py` and `strategy_promotion_watcher.py` expose summary, timeframe, entry-mode, live-eligibility, and promotion status.
- Endpoints include `/strategy-performance/summary`, `/strategy-performance/timeframes`, `/strategy-performance/entry-modes`, `/strategy-performance/live-eligibility`, and `/strategy-promotion/status`.

Risk contract layer:
- `tiny_live_risk_contract.py` reads `configs/hammer_radar/tiny_live_risk_contracts.json`.
- Current local risk config exists for BTCUSDT 13m long `ladder_close_50_618`, with max margin 44 USDT, max loss 4.44 USDT, isolated margin, leverage 1, protective stop required, and take profit required.

Human review layer:
- R85 ticket builder, R86 checklist, R88 final review packet, R89 human confirmation records, and R90 readiness snapshot form the current review chain.
- The chain is review-only and currently blocked by missing persisted human review records.

Execution boundary layer:
- `binance_live_status.py`, `live_env_boundary_review.py`, `live_safety.py`, `live_preflight.py`, and `execution/binance_futures_connector.py` define live and Binance boundaries.
- Current boundaries preserve `live_execution_enabled=false`, `allow_live_orders=false`, `global_kill_switch=true`, `order_placed=false`, `real_order_placed=false`, and `execution_attempted=false`.

Telegram operator layer:
- `notification_watcher.py`, `telegram_operator_bridge.py`, `telegram_approval_challenge.py`, and `telegram_polling_worker.py` provide alert, command, and approval-intent surfaces.
- Telegram approval records intent only; it does not arm or execute live orders.

Service/runtime layer:
- Known local services include `hammer-approval-api.service`, `hammer-telegram-polling.service`, and `hammer-paper-refresh.service`.
- Service status must be checked by the operator; R101 did not start, stop, restart, enable, or disable services.

## 3. Live Readiness Checklist

| Item | Status | Evidence / notes |
|---|---|---|
| approval API service | UNKNOWN | Code and route surfaces are present in `approval_api.py`; runtime service status requires `systemctl` check. |
| radar service | UNKNOWN | Scanner/source modules exist; runtime service status was not statically confirmed. |
| paper refresh service | UNKNOWN | Scheduler and systemd files/tests exist; runtime service status requires operator check. |
| Telegram polling service | UNKNOWN | Polling worker and endpoint exist; runtime service status requires operator check. |
| paper candidate generation | PRESENT | Scanner, market-intelligence, Miro Fish, Markov, and candidate-watch modules exist. |
| paper execution ledger | PRESENT | `paper_execution.py` and `/paper-executions` exist; ledger is paper-only. |
| strategy performance summary | PRESENT | `/strategy-performance/summary` and `strategy_performance.py` exist. |
| timeframe performance | PRESENT | `/strategy-performance/timeframes` exists. |
| entry mode performance | PRESENT | `/strategy-performance/entry-modes` exists. |
| live eligibility evaluation | PRESENT_BUT_BLOCKED | `/strategy-performance/live-eligibility` exists; live execution remains disabled and gated. |
| strategy promotion status | PRESENT | `/strategy-promotion/status` exists. |
| tiny live risk contract config | PRESENT | `configs/hammer_radar/tiny_live_risk_contracts.json` exists and hash is present. |
| live arming preflight | PRESENT_BUT_BLOCKED | `/live-arming/preflight` exists; current R84 status is blocked by missing operator approval. |
| env boundary review | PRESENT_BUT_BLOCKED | `/live-arming/env-boundary-review` exists; current R87 status is `LIVE_ENV_ARMING_NOT_ALLOWED_YET`. |
| Binance connectivity/status | PRESENT_BUT_BLOCKED | Read-only status exists; current builder reports missing credentials, live env not loaded, and no network use. |
| global kill switch behavior | PRESENT_BUT_BLOCKED | Current static status keeps `global_kill_switch=true`. |
| live execution enabled flag | PRESENT_BUT_BLOCKED | Current status keeps `live_execution_enabled=false`. |
| live order allowed flag | PRESENT_BUT_BLOCKED | Current status keeps `allow_live_orders=false`. |
| final review packet | PRESENT_BUT_BLOCKED | R88 packet builder exists; current source chain reports final approval not recorded and R87 boundary blocked. |
| human confirmation phrase | PRESENT_BUT_BLOCKED | Required phrases are generated by R85/R86/R88/R89, but required records are missing. |
| Telegram alert path | PRESENT | Notification watcher and Telegram polling surfaces exist; alert-only by design. |
| Telegram approval path | PRESENT_BUT_BLOCKED | Exact approval/challenge flow exists, but remains approval intent only and does not execute. |
| stale candidate protection | PRESENT | Freshness/stale checks exist in live approval, preflight, notification, and tests. |
| order placement boundary | PRESENT_BUT_BLOCKED | Connector blocks live order by mode, env flags, approval, test order, protective order, adapter, and kill switch gates. |
| audit logs / ledgers | PRESENT | NDJSON ledgers exist for approvals, tickets, paper execution, attempts, notifications, confirmations, and packets. |

## 4. Non-Bypassable Live Rules

These rules must remain true before any live order path can be considered:
- No live order from signal alone.
- No live order from Telegram alert alone.
- No live order without risk contract hash.
- No live order without final review packet hash.
- No live order without explicit human confirmation phrase.
- No live order if candidate is stale.
- No live order if environment boundary is blocked.
- No live order if live execution flags disagree.
- No live order if Binance boundary/status is unsafe.
- No live order if global kill switch blocks execution.
- No live order without exact signal-bound approval intent.
- No live order without validated protective stop and take-profit path.
- No live order without the future phase explicitly authorizing execution.

## 5. Known Blockers

Current code/config/static-output blockers:
- R85 ticket approval is not recorded for review.
- R86 checklist confirmations are not recorded for review.
- R88 final human approval is not recorded for review.
- R89 human confirmation records are missing all required record types.
- R84 is blocked by missing operator approval.
- R87 live env boundary remains blocked by execution boundary, no real balance check, missing operator approval, missing ticket approval, and missing checklist.
- R90 readiness snapshot is review-only, missing review records, blocked by R87 boundary, and non-executable.
- Binance status is blocked by application default disabled live execution, active global kill switch, missing API key, missing API secret, and live order placement not implemented in the read-only status surface.
- Binance connector status is blocked by `DRY_RUN_ONLY` mode.
- Protective orders are disabled and remain in `PREVIEW_ONLY` mode.
- Protective order support/readiness is false.
- Live order adapter is not configured.
- Test-order network is disabled.
- Signed payload creation is unavailable in current status because secrets are not present in the current process env.
- Account balance/funding remains a manual operator unknown; the config explicitly reports `account_balance_checked=false`.

Overlapping or duplicate-risk areas to preserve for future cleanup:
- Multiple readiness checks: `/readiness`, R42 live preflight, R84 live arming preflight, R87 env boundary, R90 readiness snapshot, R76/R78 first-live readiness modules.
- Multiple live env flag validators: `binance_live_status.py`, `execution/binance_futures_connector.py`, `live_env_boundary_review.py`, `live_safety.py`, and older live-gate modules.
- Duplicate Binance boundary checks: read-only Binance status, connector status, payload preview, test-order, protective-order, and execute paths each re-check parts of the boundary.
- Overlapping final review packet logic: R88 packet generation, R89 confirmation records, and R90 hash-chain aggregation all reconstruct related source snapshots.
- Overlapping Telegram notification/approval logic: notification watcher, operator command bridge, approval challenge, and polling worker all expose operator surfaces.
- Duplicate paper/live eligibility checks: strategy performance live eligibility, promotion watcher, trade ticket, live preflight, first-live gates, and current R84/R90 review chain.

Recommendation: do not refactor these in R101. A future phase should designate one read-only aggregation source and keep existing endpoints as adapters.

## 6. Unknowns Requiring Operator Check

Cannot be confirmed statically from code without explicit operator action:
- Whether `hammer-approval-api.service` is installed, enabled, active, and bound only to local/private interfaces.
- Whether `hammer-telegram-polling.service` is installed, enabled, active, and using the expected token/chat configuration.
- Whether `hammer-paper-refresh.service` is installed, enabled, active, and writing recent paper refresh runs.
- Whether the radar scanner process is actively running and producing fresh `signals.ndjson` rows.
- Whether current paper candidates are fresh enough for any live-review window.
- Whether Binance live env file exists with correct private permissions.
- Whether Binance API key/secret are configured in a safe private env file.
- Whether account funding is actually present; R101 intentionally did not check balances.
- Whether operator has completed all exact human phrases.
- Whether any later explicit phase has authorized env arming or live execution.

## 7. Recommended Next Phases

- R102 one-command final preflight: add a single read-only command/API report that aggregates R84, R87, R88, R89, R90, Binance status, protective status, service status hints, and stale-candidate status without adding a new source of truth.
- R103 Telegram final approval flow: make Telegram guide and record the exact R85/R86/R88 review phrases, still non-executable and still blocked by R87/R90 unless all hashes match.
- R104 tiny-live armed dry run: run the whole chain with live env intent still non-executing, exercising payload/test/protective checks only through explicit dry-run or mock paths.
- R105 one tiny live order protocol: only after R102-R104 pass, define the operator-controlled protocol for one protected tiny live order with explicit future authorization, kill switch review, balance check authorization, protective stop/take-profit guarantee, and post-order audit.

## 8. Validation Commands

Service checks:

```bash
systemctl status hammer-approval-api.service --no-pager
systemctl status hammer-telegram-polling.service --no-pager
systemctl status hammer-paper-refresh.service --no-pager
```

Endpoint checks:

```bash
curl -s http://127.0.0.1:8015/health | jq .
curl -s http://127.0.0.1:8015/readiness | jq .
curl -s http://127.0.0.1:8015/paper-executions | jq .
curl -s 'http://127.0.0.1:8015/trade-ticket' | jq .
curl -s http://127.0.0.1:8015/notifications/status | jq .
curl -s -X POST http://127.0.0.1:8015/notifications/check -H 'Content-Type: application/json' -d '{"send":false,"channel":"telegram"}' | jq .
curl -s http://127.0.0.1:8015/notifications/alerts | jq .
curl -s http://127.0.0.1:8015/strategy-performance/summary | jq .
curl -s http://127.0.0.1:8015/strategy-performance/timeframes | jq .
curl -s http://127.0.0.1:8015/strategy-performance/entry-modes | jq .
curl -s http://127.0.0.1:8015/strategy-performance/live-eligibility | jq .
curl -s http://127.0.0.1:8015/strategy-promotion/status | jq .
curl -s http://127.0.0.1:8015/live-arming/preflight | jq .
curl -s http://127.0.0.1:8015/live-arming/env-boundary-review | jq .
curl -s http://127.0.0.1:8015/live-arming/readiness-snapshot | jq .
curl -s http://127.0.0.1:8015/binance-live/status | jq .
curl -s http://127.0.0.1:8015/binance-live/connector-status | jq .
curl -s http://127.0.0.1:8015/binance-live/protective-status | jq .
```

Inspect CLI checks:

```bash
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readiness
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward live-arming-preflight
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-risk-contract
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-ticket
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward live-env-boundary-review
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-review-packet
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward human-confirmations
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward readiness-snapshot
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward notification-status
PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward paper-refresh-status
```

Test command:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/hammer_radar
```

Focused fallback tests if the full suite fails for unrelated existing reasons:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/hammer_radar/test_approval_api.py \
  tests/hammer_radar/test_live_preflight.py \
  tests/hammer_radar/test_final_protected_live_gate_review.py \
  tests/hammer_radar/test_notification_watcher.py \
  tests/hammer_radar/test_telegram_operator_bridge.py \
  tests/hammer_radar/test_telegram_polling_worker.py \
  tests/hammer_radar/test_paper_refresh_scheduler.py \
  tests/hammer_radar/test_execution_safety.py \
  tests/hammer_radar/test_binance_futures_connector.py
```

## Capability Reuse Notes

Existing modules reused for this audit:
- `approval_api.py`
- `readiness.py`
- `strategy_performance.py`
- `strategy_promotion_watcher.py`
- `live_arming_preflight.py`
- `live_env_boundary_review.py`
- `review_record_aggregator.py`
- `final_human_review_packet.py`
- `human_confirmation_records.py`
- `tiny_live_risk_contract.py`
- `tiny_live_ticket_builder.py`
- `notification_watcher.py`
- `telegram_operator_bridge.py`
- `telegram_approval_challenge.py`
- `telegram_polling_worker.py`
- `paper_refresh_scheduler.py`
- `binance_live_status.py`
- `execution/binance_futures_connector.py`
- `execution/safety.py`

Existing docs reused:
- `README.md`
- `docs/hammer_radar/PHASE_CAPABILITY_INDEX_R1_R100.md`
- `docs/hammer_radar/R69_TELEGRAM_POLLING_RUNBOOK.md`
- `docs/hammer_radar/R74_POLICY_ARMING_RUNBOOK.md`
- `docs/hammer_radar/R75_POLICY_ARMED_DRY_CHAIN_SMOKE.md`
- `docs/hammer_radar/R76_FUNDED_TINY_LIVE_READINESS.md`
- `docs/hammer_radar/R78_REHEARSAL_TEST_ORDER_PROTECTIVE_READINESS.md`
- `docs/hammer_radar/R79_FINAL_PROTECTED_LIVE_GATE_REVIEW.md`
- `docs/hammer_radar/R84_LIVE_FUNDING_FINAL_ARMING_PREFLIGHT.md`
- `docs/hammer_radar/R84_1_TINY_LIVE_RISK_CONTRACT_CONFIG.md`
- `docs/hammer_radar/R85_EXACT_OPERATOR_APPROVAL_NON_EXECUTABLE_TICKET_BUILDER.md`
- `docs/hammer_radar/R86_LIVE_ENV_ARMING_CHECKLIST_MANUAL_FUNDING_CONFIRMATION.md`
- `docs/hammer_radar/R87_LIVE_ENV_TOGGLE_DESIGN_EXECUTION_BOUNDARY_REVIEW.md`
- `docs/hammer_radar/R88_FINAL_HUMAN_APPROVAL_RECORD_REVIEW_PACKET.md`
- `docs/hammer_radar/R89_HUMAN_CONFIRMATION_WRITE_FLOW_REVIEW_RECORD_PERSISTENCE.md`
- `docs/hammer_radar/R89_1_HUMAN_CONFIRMATION_API_HASH_CHAIN_HOTFIX.md`
- `docs/hammer_radar/R90_REVIEW_RECORD_AGGREGATOR_ARMING_READINESS_SNAPSHOT.md`
- `docs/hammer_radar/R93_R84_PREFLIGHT_BLOCKER_HIERARCHY_REPAIR.md`
- `docs/hammer_radar/R94_CURRENT_CANDIDATE_REVALIDATION_MARKOV_SUPPORT_WATCH.md`

Existing endpoints inspected:
- `/health`
- `/readiness`
- `/paper-executions`
- `/trade-ticket`
- `/notifications/status`
- `/notifications/check`
- `/notifications/alerts`
- `/strategy-performance/summary`
- `/strategy-performance/timeframes`
- `/strategy-performance/entry-modes`
- `/strategy-performance/live-eligibility`
- `/strategy-promotion/status`
- `/live-arming/preflight`
- `/live-arming/env-boundary-review`

Why this is not duplicating prior work:
- R101 creates only an index document. It does not add a new readiness function, endpoint, CLI command, ledger, scheduler task, or execution path.
- Existing readiness builders remain the source of current blocker evidence.
- Future aggregation is recommended for R102 as an adapter over existing surfaces, not a replacement.
