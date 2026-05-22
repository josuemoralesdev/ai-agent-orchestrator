# Agent Workflow

This workflow adapts the specialized-agent task-folder pattern to Hammer Radar / Money Printing Machine phases. It is a Codex workflow layer only. It does not change runtime trading behavior.

## Role Files

Use these repo-root role files as perspective checklists:

- `AGENTS.builder.md`: implementation discipline, scoped edits, tests, and final report.
- `AGENTS.index.md`: phase index, capability map, duplicate-risk scan, and source-of-truth map.
- `AGENTS.qa.md`: validation plan, exact pass/fail reporting, smoke checks, and safety assertions.
- `AGENTS.security.md`: live trading safety, secret handling, Binance boundaries, approval semantics, and operational limits.

## Builder Agent Role

The builder implements only the assigned phase. It reuses existing Hammer Radar capabilities first, avoids duplicate readiness engines, preserves live-trading safety defaults, and reports changed files and validation results. The builder does not commit, merge, tag, push, deploy, run `sudo`, or repair Git permissions.

## Index Agent Role

The index role maps existing capabilities before new work starts. It keeps phase indexes current, links R101-R106 and planned R107 docs, identifies duplicate-risk areas, and maintains the source-of-truth map. The index role does not change runtime behavior.

## QA / Tester Agent Role

The QA role runs focused validation first, then broader checks when scope warrants. It reports exact commands and exact pass/fail. It verifies safety assertions including no order placement, no real order placement, no execution attempt, no secret exposure, kill-switch discipline, and paper/live separation.

## Security Agent Role

The security role reviews live-trading boundaries, secret handling, Binance rules, Telegram approval semantics, dry-run behavior, kill-switch behavior, and ledger permission failure handling. It treats Telegram approval as intent only, not execution authority.

## How Codex Should Use These Role Files

For each phase:

1. Read `AGENTS.md` and `codex_tasks/CODEX_RULES.md`.
2. Read the assigned task file from `codex_tasks/phases/`.
3. Read the relevant role files listed under assigned agents.
4. Perform the capability scan before editing.
5. Apply builder, index, QA, and security perspectives as applicable.
6. Implement only the requested phase.
7. Run required validation.
8. Report only.

Codex may apply the perspectives in one run, but the final report must state which agent perspectives were applied.

## Phase Report Requirements

Each substantial phase report should include:

- branch
- phase classification
- agent perspectives applied
- capability scan summary
- reuse / extend / create decision
- duplicate risk report
- files created and modified
- validation commands and results
- runtime behavior changed or not
- safety result
- blockers and manual commands, if any

## Operational Rules

- No `sudo` inside Codex.
- Operator handles commit, merge, and tag manually unless explicitly delegated.
- Branch and tag naming must differ.
- Branch example: `r107-first-live-execution-phase-design`.
- Tag example: `r107`.
- Never use the same exact name for a branch and tag.
- Do not start, stop, restart, enable, or disable services unless explicitly instructed.
- Live trading requires explicit user authorization in the future phase task and in the current turn.

