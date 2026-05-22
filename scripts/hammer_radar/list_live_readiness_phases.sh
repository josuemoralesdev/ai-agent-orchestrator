#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Live-readiness docs:"
find "$repo_root/docs/hammer_radar/live_readiness" -maxdepth 1 -type f -name '*.md' | sort

echo
echo "Phase task files:"
find "$repo_root/codex_tasks/phases" -maxdepth 1 -type f -name '*.md' | sort

