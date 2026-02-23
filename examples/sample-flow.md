# Sample Flow

Scenario: user requests an action that may require payment and external provider execution.

## Steps

1. Receive inbound request via webhook
2. Extract intent and required identifiers
3. Request missing information if needed
4. Generate structured tool call
5. Optional human approval checkpoint
6. Execute provider adapter
7. Normalize response
8. Return result and log trace

## Goal

Demonstrate safe orchestration of AI-driven actions in real-world workflows.