"""Non-trading Binance adapter boundary for future integration."""

from __future__ import annotations

from src.app.hammer_radar.execution.base import AccountSnapshot, OrderResult
from src.app.hammer_radar.operator.models import PaperPosition, SignalRecord


class BinanceStubAdapter:
    name = "binance_stub"
    mode = "binance_stub"

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            adapter_name=self.name,
            mode=self.mode,
            paper_only=True,
            balances={},
            notes=(
                "Binance stub boundary only.",
                "Live trading is disabled.",
            ),
        )

    def get_open_positions(self) -> list[PaperPosition]:
        return []

    def place_order(self, signal: SignalRecord) -> OrderResult:
        raise NotImplementedError(
            f"{self.name} cannot place live orders. Live trading is disabled for signal {signal.signal_id}."
        )

    def close_position(
        self,
        position: PaperPosition,
        *,
        exit_price: float,
        close_reason: str,
        closed_at: str,
    ) -> OrderResult:
        raise NotImplementedError(
            f"{self.name} cannot close live positions. Live trading is disabled for {position.position_id}."
        )

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(
            adapter_name=self.name,
            mode=self.mode,
            accepted=False,
            status="noop",
            message="Binance stub does not manage real orders. Live trading is disabled.",
            details={"order_id": order_id},
        )
