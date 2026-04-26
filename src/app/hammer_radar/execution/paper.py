"""Deterministic local paper execution adapter."""

from __future__ import annotations

from src.app.hammer_radar.execution.base import AccountSnapshot, OrderResult
from src.app.hammer_radar.operator.models import PaperPosition, SignalRecord
from src.app.hammer_radar.operator.positions import (
    DEFAULT_ENTRY_MODE,
    DEFAULT_POSITION_SIZE_USD,
    close_position as close_paper_position,
    create_paper_position,
    load_open_positions,
)
from src.app.hammer_radar.operator.strategy_config import is_entry_mode_allowed, load_strategy_config


class PaperExecutionAdapter:
    name = "paper"
    mode = "paper"

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            adapter_name=self.name,
            mode=self.mode,
            paper_only=True,
            balances={"USD": 0.0},
            notes=(
                "Paper execution only.",
                "No live Binance trading is enabled.",
            ),
        )

    def get_open_positions(self) -> list[PaperPosition]:
        return load_open_positions()

    def place_order(self, signal: SignalRecord) -> OrderResult:
        strategy_config = load_strategy_config()
        if not strategy_config.paper_enabled:
            return OrderResult(
                adapter_name=self.name,
                mode=self.mode,
                accepted=False,
                position=None,
                status="rejected",
                message="Paper execution is disabled by strategy config.",
                details={"signal_id": signal.signal_id},
            )
        if not is_entry_mode_allowed(DEFAULT_ENTRY_MODE, strategy_config):
            return OrderResult(
                adapter_name=self.name,
                mode=self.mode,
                accepted=False,
                position=None,
                status="rejected",
                message="Default paper entry mode is blocked by strategy config.",
                details={"signal_id": signal.signal_id, "entry_mode": DEFAULT_ENTRY_MODE},
            )
        position = create_paper_position(
            signal,
            entry_mode=DEFAULT_ENTRY_MODE,
            size_usd=DEFAULT_POSITION_SIZE_USD,
        )
        if position is None:
            return OrderResult(
                adapter_name=self.name,
                mode=self.mode,
                accepted=False,
                position=None,
                status="rejected",
                message="Paper position was not created.",
                details={"signal_id": signal.signal_id, "entry_mode": DEFAULT_ENTRY_MODE},
            )
        return OrderResult(
            adapter_name=self.name,
            mode=self.mode,
            accepted=True,
            position=position,
            status="opened",
            message="Paper position created.",
            details={"signal_id": signal.signal_id, "entry_mode": DEFAULT_ENTRY_MODE},
        )

    def close_position(
        self,
        position: PaperPosition,
        *,
        exit_price: float,
        close_reason: str,
        closed_at: str,
    ) -> OrderResult:
        closed_position = close_paper_position(
            position,
            exit_price=exit_price,
            close_reason=close_reason,
            closed_at=closed_at,
        )
        return OrderResult(
            adapter_name=self.name,
            mode=self.mode,
            accepted=True,
            position=closed_position,
            status="closed",
            message="Paper position closed.",
            details={"close_reason": close_reason},
        )

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(
            adapter_name=self.name,
            mode=self.mode,
            accepted=False,
            status="noop",
            message="Paper execution does not maintain cancellable live orders.",
            details={"order_id": order_id},
        )
