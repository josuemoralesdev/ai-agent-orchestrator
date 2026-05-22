# Live Readiness Phase Index

This index maps the R101-R107 first-live readiness path. It is documentation only and does not change runtime trading behavior.

| Phase | Status | Purpose | Primary Command | Safety State | Artifact / Doc Path | Agent Roles |
|---|---|---|---|---|---|---|
| R101 live readiness index | Complete | Repo-grounded index of live-readiness surfaces and blockers before tiny-live arming. | None; review document only. | BLOCKED; no live trading, no env changes, no orders. | `docs/hammer_radar/live_readiness/R101_LIVE_READINESS_INDEX.md` | index, security |
| R102 final live preflight | Complete | One read-only final preflight composition over existing readiness, boundary, review, Binance-status, and notification surfaces. | `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward final-live-preflight` | Reports `READY` or `BLOCKED`; no order placement, no Binance order calls, no env edits. | `docs/hammer_radar/live_readiness/R102_ONE_COMMAND_FINAL_PREFLIGHT.md` | builder, index, qa, security |
| R103 Telegram final approval intent | Complete | Telegram final preflight and approval-intent recording that reuses R102. | Telegram: `/final_preflight`, `/approve_final <candidate_id> <risk_contract_hash> <packet_hash>` | Approval intent only; Telegram is not execution authority. | `docs/hammer_radar/live_readiness/R103_TELEGRAM_FINAL_APPROVAL_FLOW.md` | builder, index, qa, security |
| R104 tiny-live armed dry run | Complete | Exercise the arming chain as dry-run evidence while proving no real order can be placed. | `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-armed-dry-run` | Dry-run only; `live_ready=false`, `order_placed=false`, `execution_attempted=false`. | `docs/hammer_radar/live_readiness/R104_TINY_LIVE_ARMED_DRY_RUN.md` | builder, index, qa, security |
| R105 one tiny live order protocol | Complete | Define and optionally check the protocol prerequisites for one future protected tiny live order. | `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward one-tiny-live-order-protocol` | Protocol only; not live readiness and not execution authority. | `docs/hammer_radar/live_readiness/R105_ONE_TINY_LIVE_ORDER_PROTOCOL.md` | builder, index, qa, security |
| R106 first-live activation gate | Complete | Compose R102-R105 evidence into the final non-executing activation gate before any future execution phase. | `PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward first-live-activation-gate` | Returns `FIRST_LIVE_BLOCKED` or `FIRST_LIVE_ACTIVATION_READY`; still non-executing. | `docs/hammer_radar/live_readiness/R106_FIRST_LIVE_ACTIVATION_GATE.md` | builder, index, qa, security |
| R106.5 specialized agent task workflow integration | Complete | Add specialized agent role files, phase task folders, workflow docs, and an R107 draft task. | None; workflow/documentation phase only. | No runtime changes, no live trading, no order calls, no env edits. | `docs/hammer_radar/live_readiness/AGENT_TASK_WORKFLOW.md`, `codex_tasks/phases/R107_FIRST_LIVE_EXECUTION_PHASE_DESIGN.md` | builder, index, qa, security |
| R107 planned first-live execution phase design | Planned draft | Design the first-live execution phase requirements after R106 without implementing execution behavior. | None in draft; any future command requires explicit phase authorization. | Planned design only; no live order placement unless separately authorized in a future phase. | `codex_tasks/phases/R107_FIRST_LIVE_EXECUTION_PHASE_DESIGN.md` | builder, index, qa, security |

## Source-Of-Truth Notes

- R102 is the current final live preflight composition surface.
- R103 records approval intent; it does not authorize execution.
- R104 records dry-run evidence; it does not make the system live-ready.
- R105 defines protocol prerequisites; it does not place orders.
- R106 reports activation readiness for a future phase; it does not enable execution.
- R107 remains planned design until a future explicit authorization changes scope.

