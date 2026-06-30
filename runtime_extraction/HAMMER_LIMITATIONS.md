# Hammer Limitations

## Trading Limits

Hammer is a radar and safety system, not autonomous live trading authority. It can identify candidates, prepare paper or review artifacts, and explain readiness. It cannot treat a signal, score, ticket, alert, or approval record as enough to place a real order.

## Market Reality Limits

Hammer's market view depends on available candle data and local archives. A missing, stale, malformed, or incomplete candle source can weaken signal extraction, Markov/Miro Fish checks, source-chain support, and freshness decisions.

Hammer can classify a candidate as fresh or expired only relative to its observed timestamp and configured freshness window.

## Strategy Evidence Limits

Strategy memory is only as strong as recorded samples. Low sample count, missing explicit entry mode, missing outcome rows, stale promotion state, or source-chain gaps can block live qualification.

Win rate, average PnL, Markov support, Miro Fish support, and betrayal analysis are evidence. They are not guarantees.

## Operator Limits

Operator records are explicit and durable, but they do not bypass safety. Human confirmation records, approval intent, Telegram replies, or paper-ticket approval can satisfy review requirements, but execution still needs live flags, kill switch posture, dry-run validity, protective readiness, and final execution gates.

## Execution Limits

Default Hammer execution is paper-only. The live connector stub records rejected attempts. Live execution paths remain blocked unless future explicit approved phases enable the required flags and pass all safety gates.

Current limitations include:

- no default real order placement
- no default Binance order endpoint calls
- no default account balance or funding calls
- no default signed live trading request creation
- no secret exposure
- no public approval API exposure intended
- no automatic live promotion from paper results

## Risk Contract Limits

Tiny-live risk contracts are lane-specific and cap notional, leverage, and max loss. Hammer rejects hidden leverage expansion, cross-lane borrowing, missing lane identity, missing max loss, and live-enabled contract state when it is not explicitly allowed.

Risk contract validity does not mean live execution readiness.

## Lane Limits

Lane controls express exact operator intent for one lane key. A lane being configured as `tiny_live` or armed dry-run does not bypass global gates. If the global gate is not ready, the lane remains blocked for live execution.

## Safety Limits

Hammer's safest answer is often "blocked." It intentionally carries repeated blockers across preflight, readiness, lane, and connector surfaces. This can feel redundant, but it protects against accidental conversion of review evidence into execution authority.

## Documentation Extraction Limits

This extraction is based on Hammer-specific docs, modules, tests, configs, and the R334 phase brief visible in this workspace. It avoids MasonShift Core and does not attempt to rename Hammer concepts into another subsystem's vocabulary.
