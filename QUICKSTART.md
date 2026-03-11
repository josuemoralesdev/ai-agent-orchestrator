## Quickstart

### Requirements

- Python 3.11+
- `pip`
- virtual environment support

### Setup

```bash
git clone https://github.com/josuemoralesdev/ai-agent-orchestrator.git
cd ai-agent-orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run locally

```bash
uvicorn src.main:app --reload
```

The service should now be available at:

```bash
http://127.0.0.1:8000
```

---

## Health Check

```bash
curl -s http://127.0.0.1:8000/health | jq
```

Example response:

```json
{
  "status": "ok",
  "service": "kernel",
  "version": "0.1.0"
}
```

---

## Example API Usage

### 1. Plan a request

```bash
curl -s -X POST http://127.0.0.1:8000/plan \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "ops_demo",
    "channel": "api",
    "message": "Generate a payment link for order #4821 for 1250 MXN and send it back to the customer."
  }' | jq
```

Example response:

```json
{
  "trace_id": "trc_01HXYZ9A8K",
  "intent": "create_payment_link",
  "requires_approval": true,
  "status": "planned",
  "entities": {
    "order_id": "4821",
    "amount": 1250,
    "currency": "MXN"
  }
}
```

---

### 2. Approve the plan

```bash
curl -s -X POST http://127.0.0.1:8000/approve \
  -H "Content-Type: application/json" \
  -d '{
    "trace_id": "trc_01HXYZ9A8K",
    "decision": "approved",
    "approved_by": "ops_manager",
    "notes": "Approved for order 4821."
  }' | jq
```

Example response:

```json
{
  "trace_id": "trc_01HXYZ9A8K",
  "status": "approved",
  "message": "Plan approved and ready for execution."
}
```

---

### 3. Execute the approved workflow

```bash
curl -s -X POST http://127.0.0.1:8000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "trace_id": "trc_01HXYZ9A8K"
  }' | jq
```

Example response:

```json
{
  "trace_id": "trc_01HXYZ9A8K",
  "status": "completed",
  "result": {
    "payment_link_id": "pay_8FJ29KLM",
    "payment_url": "https://payments.example.com/pay_8FJ29KLM"
  }
}
```

---

### 4. Retrieve the execution trace

```bash
curl -s http://127.0.0.1:8000/trace/trc_01HXYZ9A8K | jq
```

Example response:

```json
{
  "trace_id": "trc_01HXYZ9A8K",
  "status": "completed",
  "lifecycle": [
    {
      "event": "request_received",
      "timestamp": "2026-03-11T09:10:00Z"
    },
    {
      "event": "plan_generated",
      "timestamp": "2026-03-11T09:10:02Z"
    },
    {
      "event": "policy_validated",
      "timestamp": "2026-03-11T09:10:03Z"
    },
    {
      "event": "approval_received",
      "timestamp": "2026-03-11T09:11:12Z"
    },
    {
      "event": "tool_executed",
      "timestamp": "2026-03-11T09:11:20Z"
    },
    {
      "event": "response_returned",
      "timestamp": "2026-03-11T09:11:21Z"
    }
  ]
}
```