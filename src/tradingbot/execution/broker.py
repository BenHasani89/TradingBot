"""Paper Trading Broker."""

from __future__ import annotations

from tradingbot.execution.models import (
    ExecutionResult,
    Order,
)


class PaperBroker:
    """Simulierter Broker ohne echtes Geld."""

    def __init__(self) -> None:
        self.orders: list[Order] = []

    def execute(
        self,
        order: Order,
    ) -> ExecutionResult:
        """Führt eine virtuelle Order aus."""

        self.orders.append(order)

        return ExecutionResult(
            success=True,
            order=order,
            message="Paper Order ausgeführt",
        )

    def history(self) -> list[Order]:
        """Gibt ausgeführte Orders zurück."""

        return self.orders
