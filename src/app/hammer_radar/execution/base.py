"""Execution adapter interfaces for Hammer Radar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.app.hammer_radar.operator.models import PaperPosition, SignalRecord


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    adapter_name: str
    mode: str
    paper_only: bool
    balances: dict[str, float]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OrderResult:
    adapter_name: str
    mode: str
    accepted: bool
    position: PaperPosition | None = None
    status: str = "noop"
    message: str = ""
    details: dict[str, Any] | None = None


class ExecutionAdapter(Protocol):
    name: str
    mode: str

    def get_account_snapshot(self) -> AccountSnapshot: ...

    def get_open_positions(self) -> list[PaperPosition]: ...

    def place_order(self, signal: SignalRecord) -> OrderResult: ...

    def close_position(
        self,
        position: PaperPosition,
        *,
        exit_price: float,
        close_reason: str,
        closed_at: str,
    ) -> OrderResult: ...

    def cancel_order(self, order_id: str) -> OrderResult: ...
