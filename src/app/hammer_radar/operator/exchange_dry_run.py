"""Exchange connector dry-run validation for Hammer Radar tickets.

This module prepares local exchange payload previews only. It never imports an
exchange SDK, never reads credentials, never calls the network, and never places
orders.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.readiness import LIVE_EXECUTION_ENABLED, ORDER_PLACED
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket

DRY_RUN = True
EXCHANGE_NAME = "binance_futures_dry_run"
ORDER_TYPE = "LIMIT"

BTCUSDT_RULES: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "market_type": "futures",
    "quote_asset": "USDT",
    "base_asset": "BTC",
    "min_notional_usd": 5.0,
    "tick_size": 0.10,
    "step_size": 0.001,
    "quantity_precision": 3,
    "price_precision": 1,
    "max_leverage_allowed": 3.0,
    "allowed_margin_mode": "isolated",
}

SYMBOL_RULES = {
    "BTCUSDT": BTCUSDT_RULES,
}


def build_current_exchange_dry_run(
    *,
    signal_id: str | None = None,
    allow_short: bool = False,
    max_position_usd: float = 44.0,
    max_risk_usd: float = 5.0,
    max_leverage: float = 3.0,
    fresh_minutes: int = 30,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    ticket = build_trade_ticket(
        signal_id=signal_id,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        fresh_minutes=fresh_minutes,
        log_dir=get_log_dir(log_dir, use_env=True),
    )
    return build_exchange_dry_run(ticket)


def build_exchange_dry_run(ticket: dict[str, Any]) -> dict[str, Any]:
    created_at = datetime.now(UTC)
    symbol = str(ticket.get("symbol") or "")
    rules = SYMBOL_RULES.get(symbol)
    direction = str(ticket.get("direction") or "").lower()
    entry = _float_or_none(ticket.get("entry"))
    stop = _float_or_none(ticket.get("stop"))
    take_profit = _float_or_none(ticket.get("take_profit"))
    notional = _float_or_none(ticket.get("suggested_position_usd"))
    leverage = _float_or_none(ticket.get("suggested_leverage"))
    max_leverage_allowed = _effective_max_leverage_allowed(ticket=ticket, rules=rules)
    margin_mode = str(ticket.get("margin_mode") or "")
    ticket_status = str(ticket.get("ticket_status") or "")

    side = _side(direction)
    position_side = _position_side(direction)
    quantity = (notional / entry) if notional is not None and entry not in (None, 0.0) else None
    quantity_rounded = _round_to_step(quantity, rules["step_size"]) if rules and quantity is not None else None
    entry_rounded = _round_to_step(entry, rules["tick_size"]) if rules and entry is not None else None
    stop_rounded = _round_to_step(stop, rules["tick_size"]) if rules and stop is not None else None
    take_profit_rounded = (
        _round_to_step(take_profit, rules["tick_size"]) if rules and take_profit is not None else None
    )

    validations = {
        "symbol_supported": rules is not None,
        "min_notional_ok": bool(rules and notional is not None and notional >= float(rules["min_notional_usd"])),
        "quantity_step_ok": bool(rules and quantity_rounded is not None and quantity_rounded > 0.0),
        "price_tick_ok": bool(
            rules and entry_rounded is not None and stop_rounded is not None and take_profit_rounded is not None
        ),
        "leverage_ok": bool(rules and leverage is not None and leverage <= max_leverage_allowed),
        "margin_mode_ok": bool(rules and margin_mode == str(rules["allowed_margin_mode"])),
        "stop_present": stop is not None,
        "take_profit_present": take_profit is not None,
        "ticket_status_ok": ticket_status == "PROPOSED",
    }
    blockers = _blockers(
        validations,
        direction=direction,
        ticket_blockers=ticket.get("blockers"),
        rules=rules,
        max_leverage_allowed=max_leverage_allowed,
        notional=notional,
        leverage=leverage,
        margin_mode=margin_mode,
        ticket_status=ticket_status,
    )
    validation_status = "VALID" if not blockers else "BLOCKED"

    return {
        "dry_run_id": uuid4().hex,
        "created_at": created_at.isoformat(),
        "exchange": EXCHANGE_NAME,
        "symbol": symbol or None,
        "side": side,
        "position_side": position_side,
        "order_type": ORDER_TYPE,
        "entry_price": entry,
        "stop_price": stop,
        "take_profit_price": take_profit,
        "notional_usd": notional,
        "quantity": quantity,
        "quantity_rounded": quantity_rounded,
        "entry_price_rounded": entry_rounded,
        "stop_price_rounded": stop_rounded,
        "take_profit_price_rounded": take_profit_rounded,
        "leverage": leverage,
        "margin_mode": margin_mode or None,
        "validations": validations,
        "validation_status": validation_status,
        "blockers": blockers,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "dry_run": DRY_RUN,
        "ticket": ticket,
        "exchange_order_payload_preview": _payload_preview(
            symbol=symbol,
            side=side,
            position_side=position_side,
            quantity=quantity_rounded,
            entry_price=entry_rounded,
            leverage=leverage,
            margin_mode=margin_mode,
        ),
    }


def build_exchange_dry_run_text(
    *,
    signal_id: str | None = None,
    allow_short: bool = False,
    max_position_usd: float = 44.0,
    max_leverage: float = 3.0,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_current_exchange_dry_run(
        signal_id=signal_id,
        allow_short=allow_short,
        max_position_usd=max_position_usd,
        max_leverage=max_leverage,
        log_dir=log_dir,
    )
    lines = [
        "HAMMER RADAR EXCHANGE DRY RUN",
        f"validation_status: {payload['validation_status']}",
        f"exchange: {payload['exchange']}",
        f"symbol: {payload.get('symbol') or 'n/a'}",
        f"side: {payload.get('side') or 'n/a'}",
        f"position_side: {payload.get('position_side') or 'n/a'}",
        f"notional_usd: {_format_value(payload.get('notional_usd'))}",
        f"quantity_rounded: {_format_value(payload.get('quantity_rounded'))}",
        f"entry_price_rounded: {_format_value(payload.get('entry_price_rounded'))}",
        f"stop_price_rounded: {_format_value(payload.get('stop_price_rounded'))}",
        f"take_profit_price_rounded: {_format_value(payload.get('take_profit_price_rounded'))}",
        f"leverage: {_format_value(payload.get('leverage'))}",
        f"margin_mode: {payload.get('margin_mode') or 'n/a'}",
        f"blockers: {'; '.join(payload['blockers']) if payload['blockers'] else 'none'}",
        "live_execution_enabled: false",
        "order_placed: false",
        "dry_run: true",
        "No order was sent.",
        "No API key used.",
    ]
    return "\n".join(lines)


def _blockers(
    validations: dict[str, bool],
    *,
    direction: str,
    ticket_blockers: object,
    rules: dict[str, Any] | None,
    max_leverage_allowed: float,
    notional: float | None,
    leverage: float | None,
    margin_mode: str,
    ticket_status: str,
) -> list[str]:
    blockers: list[str] = []
    if not validations["symbol_supported"]:
        blockers.append("unknown symbol")
    if direction not in {"long", "short"}:
        blockers.append("direction must be long or short")
    if not validations["ticket_status_ok"]:
        blockers.append(f"ticket_status must be PROPOSED, got {ticket_status or 'missing'}")
    if ticket_blockers:
        blockers.extend(str(blocker) for blocker in ticket_blockers if blocker)
    if not validations["min_notional_ok"]:
        minimum = rules["min_notional_usd"] if rules else "n/a"
        blockers.append(f"notional below min_notional_usd {minimum}: {notional}")
    if not validations["quantity_step_ok"]:
        blockers.append("quantity does not satisfy positive step_size rounding")
    if not validations["price_tick_ok"]:
        blockers.append("price fields do not satisfy tick_size rounding")
    if not validations["leverage_ok"]:
        maximum = max_leverage_allowed if rules else "n/a"
        blockers.append(f"leverage above max {maximum}: {leverage}")
    if not validations["margin_mode_ok"]:
        expected = rules["allowed_margin_mode"] if rules else "isolated"
        blockers.append(f"margin_mode must be {expected}, got {margin_mode or 'missing'}")
    if not validations["stop_present"]:
        blockers.append("missing stop")
    if not validations["take_profit_present"]:
        blockers.append("missing take_profit")
    return list(dict.fromkeys(blockers))


def _effective_max_leverage_allowed(*, ticket: dict[str, Any], rules: dict[str, Any] | None) -> float:
    default = float((rules or {}).get("max_leverage_allowed") or 0.0)
    if (
        ticket.get("active_contract_mode") == "explicit_notional_cap_with_leverage"
        and _float_or_none(ticket.get("active_contract_max_notional_usdt")) == 80.0
        and _float_or_none(ticket.get("active_contract_leverage")) == 10.0
    ):
        return 10.0
    return default


def _payload_preview(
    *,
    symbol: str,
    side: str | None,
    position_side: str | None,
    quantity: float | None,
    entry_price: float | None,
    leverage: float | None,
    margin_mode: str,
) -> dict[str, Any]:
    return {
        "preview_only": True,
        "sent": False,
        "exchange": EXCHANGE_NAME,
        "symbol": symbol,
        "side": side,
        "positionSide": position_side,
        "type": ORDER_TYPE,
        "quantity": quantity,
        "price": entry_price,
        "leverage": leverage,
        "marginMode": margin_mode,
    }


def _side(direction: str) -> str | None:
    if direction == "long":
        return "BUY"
    if direction == "short":
        return "SELL"
    return None


def _position_side(direction: str) -> str | None:
    if direction == "long":
        return "LONG"
    if direction == "short":
        return "SHORT"
    return None


def _round_to_step(value: float | None, step: float) -> float | None:
    if value is None:
        return None
    decimal_value = Decimal(str(value))
    decimal_step = Decimal(str(step))
    rounded = (decimal_value / decimal_step).to_integral_value(rounding=ROUND_DOWN) * decimal_step
    return float(rounded)


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_value(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value)
