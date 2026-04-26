#!/usr/bin/env bash
set -e

cd /home/josue/workspace/kernel/ai-agent-orchestrator
source .venv/bin/activate
exec python -m uvicorn src.app.main:app --host 127.0.0.1 --port 8000
