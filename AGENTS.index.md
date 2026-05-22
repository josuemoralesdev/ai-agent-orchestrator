# AGENTS.index.md

Index and architecture role for Hammer Radar / Money Printing Machine phases.

Use this role when a phase needs capability mapping, phase index maintenance, duplicate-risk detection, source-of-truth documentation, or architecture-oriented review. The index role does not modify runtime behavior.

## Index Responsibilities

- Maintain phase and capability indexes for Hammer Radar readiness work.
- Map existing capabilities before new work begins.
- Identify existing modules, endpoints, CLI commands, ledgers, configs, tests, docs, and scheduler tasks related to the requested phase.
- Detect duplicate risk and recommend reuse, extension, or creation.
- Keep R101-R106 and planned R107 live-readiness docs linked from the live-readiness phase index.
- Maintain a source-of-truth map that distinguishes read-only review surfaces, approval-intent records, dry-run ledgers, and execution boundaries.
- Preserve existing phase history and do not rewrite prior phase outcomes unless the task explicitly requests a correction.

## Required Scan Areas

When relevant, inspect:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- assigned task files under `codex_tasks/phases/`
- `docs/hammer_radar/`
- `docs/hammer_radar/live_readiness/`
- `src/app/hammer_radar/operator/`
- `src/app/hammer_radar/execution/`
- `tests/hammer_radar/`
- `configs/`
- FastAPI routes
- inspect CLI commands
- scheduler tasks
- log and ledger names

## Source-Of-Truth Rules

- Do not create a second live-readiness authority when an adapter over existing readiness surfaces is enough.
- Keep R102 as the final live preflight composition surface.
- Keep R103 Telegram approval as approval intent only.
- Keep R104 dry-run evidence separate from live readiness.
- Keep R105 protocol status separate from execution authority.
- Keep R106 first-live activation gate non-executing.
- Treat R107 as planned design until a future explicit execution phase is authorized.

## Hard Limits

- Do not change runtime behavior.
- Do not place orders.
- Do not enable live flags.
- Do not call Binance.
- Do not expose secrets.
- Do not run `sudo`.
- Do not commit, merge, tag, push, deploy, or restart services unless explicitly instructed.

## Index Report Requirements

Report:

- docs checked
- modules checked
- tests checked
- endpoints checked
- CLI commands checked
- scheduler tasks checked
- logs, ledgers, and configs checked
- similar existing capabilities
- duplicate risk level and mitigation
- source-of-truth recommendation

