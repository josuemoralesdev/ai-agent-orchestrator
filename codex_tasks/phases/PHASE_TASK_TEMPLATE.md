# Phase Task Template

## Phase

`R###`

## Branch

`r###-short-phase-name`

Branch and tag names must differ. Example branch: `r107-first-live-execution-phase-design`. Example tag: `r107`.

## Phase Classification

- Primary classification:
- Secondary classification(s):
- Duplicate risk level: `LOW` / `MEDIUM` / `HIGH`

## Reason

Explain why this phase exists and what risk, blocker, or workflow gap it addresses.

## Assigned Agents

- builder:
- index:
- qa:
- security:

## Main Objective

State the single main outcome for this phase.

## Capability Scan

Inspect relevant existing surfaces before implementation:

- `AGENTS.md`
- `codex_tasks/CODEX_RULES.md`
- `codex_tasks/`
- `docs/`
- `docs/hammer_radar/`
- `docs/hammer_radar/live_readiness/`
- `src/app/hammer_radar/operator/`
- `src/app/hammer_radar/execution/`
- `tests/hammer_radar/`
- `configs/`
- FastAPI routes
- inspect CLI commands
- scheduler tasks
- logs, ledgers, and configs

Record what was checked and what existing capability can be reused.

## Reuse / Extend / Create Decision

- Existing capability reused:
- Existing capability extended:
- New capability created:
- Why new code is necessary:
- Why this does not duplicate prior work:

## Duplicate Risk Report

- Similar existing modules:
- Similar existing endpoints:
- Similar existing CLI commands:
- Similar existing scheduler tasks:
- Similar existing docs:
- Risk:
- Mitigation:

## Files Expected

List files expected to be created or changed.

## Tests Required

List focused tests or checks required for this phase.

## Validation Commands

```bash
git diff --check
```

Add focused commands as needed:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q <targeted_tests>
bash -n <script>
```

## Safety Constraints

- Do not enable live trading.
- Do not place orders.
- Do not call Binance order endpoints.
- Do not call account or balance endpoints unless explicitly authorized.
- Do not modify env flags.
- Do not expose secrets.
- Do not weaken paper/live separation.
- Preserve human approval gates.
- Preserve kill-switch discipline.

## Do Not

- Do not run `sudo`.
- Do not attempt Git permission repair.
- Do not commit.
- Do not merge.
- Do not tag.
- Do not push.
- Do not deploy.
- Do not restart production services.
- Do not modify unrelated files.

## Final Report Format

Report:

- Branch:
- Phase Classification:
- Capability scan summary:
- Reuse / Extend / Create decision:
- Duplicate risk report:
- Files created:
- Files modified:
- Tests or checks run:
- Smoke checks run, if any:
- Runtime behavior changed:
- Safety result:
- Blockers, if any:
- Exact manual commands needed, if any:

