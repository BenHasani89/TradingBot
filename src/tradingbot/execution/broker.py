"""Paper Trading Broker."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradingbot.execution.models import (
    ExecutionResult,
    ExecutionStatus,
    Order,
)


class Broker(ABC):
    """Abstrakte Ausführungsschnittstelle.

    Einzige Verantwortung: eine Order entgegennehmen und ein
    `ExecutionResult` liefern. Enthält bewusst keine Börsen-spezifische
    Logik (keine Gebühren-/Slippage-Annahmen, kein Balance-/Positions-
    Abgleich) - das bleibt Sache der jeweiligen Implementierung
    (`PaperBroker`, künftig z. B. `LiveBroker`).

    Eine Implementierung muss `order.client_order_id` unverändert in das
    zurückgegebene `ExecutionResult.order` übernehmen (nicht neu vergeben) -
    sie identifiziert die Order über ihren gesamten Lebenszyklus hinweg.
    `ExecutionResult.broker_order_id` ist die vom Broker vergebene
    Gegenstelle dazu, `ExecutionResult.status` ergänzt `success` um den
    `UNKNOWN`-Zustand für Fälle mit unklarem Ausgang (z. B. Zeitüberschreitung
    bei einem `LiveBroker`) - siehe `execution.models.ExecutionStatus`.
    """

    @abstractmethod
    def execute(self, order: Order) -> ExecutionResult:
        """Führt eine Order aus und liefert das Ergebnis."""


class PaperBroker(Broker):
    """Simulierter Broker ohne echtes Geld.

    `fee_percent` und `slippage_percent` sind Anteile (z. B. `0.001` für
    0.1 %), keine absoluten Beträge. Standard `0.0` für beide - entspricht
    exakt dem bisherigen, kostenfreien Verhalten.
    """

    def __init__(
        self,
        fee_percent: float = 0.0,
        slippage_percent: float = 0.0,
    ) -> None:
        self.orders: list[Order] = []
        self._fee_percent = fee_percent
        self._slippage_percent = slippage_percent

    @property
    def fee_percent(self) -> float:
        """Konfigurierter Gebührenanteil (z. B. `0.001` für 0.1 %)."""
        return self._fee_percent

    @property
    def slippage_percent(self) -> float:
        """Konfigurierter Slippage-Anteil (z. B. `0.001` für 0.1 %)."""
        return self._slippage_percent

    def execute(
        self,
        order: Order,
    ) -> ExecutionResult:
        """Führt eine virtuelle Order aus.

        Der Fill-Preis weicht je nach `slippage_percent` vom angefragten
        `order.price` ab (bei BUY nach oben, bei SELL nach unten - beides zum
        Nachteil des Traders, wie im echten Markt). Die Gebühr wird auf den
        tatsächlichen Ausführungswert (Fill-Preis * Menge) berechnet. Beide
        Kosten werden im `ExecutionResult` als eigene Beträge ausgewiesen,
        nicht im zurückgegebenen Preis versteckt.
        """

        if order.side == "BUY":
            fill_price = order.price * (1 + self._slippage_percent)
        else:
            fill_price = order.price * (1 - self._slippage_percent)

        slippage_cost = abs(fill_price - order.price) * order.quantity
        fee_cost = fill_price * order.quantity * self._fee_percent

        filled_order = Order(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            client_order_id=order.client_order_id,
        )
        self.orders.append(filled_order)

        return ExecutionResult(
            success=True,
            order=filled_order,
            message="Paper Order ausgeführt",
            fee=fee_cost,
            slippage=slippage_cost,
            status=ExecutionStatus.SUCCESS,
            broker_order_id=order.client_order_id,
        )

    def history(self) -> list[Order]:
        """Gibt ausgeführte Orders zurück."""

        return self.orders
