"""Order Management Layer: verwaltet den Lifecycle einzelner Orders zwischen
`TradingOrchestrator` und `Broker`.

Kapselt den Broker-Aufruf, erkennt bereits bekannte `client_order_id`
(Duplicate Detection) und bereitet künftige Reconciliation vor (siehe
`execution/order_repository.py`). Kennt keine Session-, Portfolio- oder
Risk-Konzepte - ein reiner Execution-Layer-Baustein, unterhalb von
`TradingOrchestrator`.
"""

from __future__ import annotations

from tradingbot.execution.broker import Broker
from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_repository import OrderRecord, OrderRepository

_EXECUTION_TO_ORDER_STATUS = {
    ExecutionStatus.SUCCESS: OrderStatus.FILLED,
    ExecutionStatus.FAILED: OrderStatus.FAILED,
    ExecutionStatus.UNKNOWN: OrderStatus.UNKNOWN,
}


class OrderManager:
    """Verwaltet den Lifecycle einer Order und verhindert doppelte
    Broker-Ausführungen über `client_order_id`.
    """

    def __init__(self, broker: Broker, repository: OrderRepository) -> None:
        self._broker = broker
        self._repository = repository

    def submit(self, order: Order) -> ExecutionResult:
        """Führt `order` über den Broker aus.

        Ist `order.client_order_id` bereits bekannt, wird der Broker NICHT
        erneut aufgerufen (Duplicate Detection):
        - liegt bereits ein `ExecutionResult` vor, wird dieses unverändert
          zurückgegeben.
        - liegt noch keines vor (Lifecycle zwischen `CREATED`/`SUBMITTED`
          hängengeblieben, z. B. weil ein vorheriger Broker-Aufruf mit einer
          Exception abgebrochen ist, bevor ein Ergebnis vorlag), wird ein
          `ExecutionResult` mit `status=UNKNOWN` und `success=False`
          synthetisiert - der tatsächliche Ausgang bleibt ungeklärt, dafür
          ist eine künftige Reconciliation vorgesehen.

        Andernfalls: Order als `CREATED`, dann `SUBMITTED` speichern,
        Broker aufrufen, Ergebnis speichern und Status auf den
        entsprechenden Endzustand (`FILLED`/`FAILED`/`UNKNOWN`)
        aktualisieren. Wirft der Broker-Aufruf selbst eine Exception, bleibt
        der zuletzt gespeicherte Zustand bei `SUBMITTED` stehen - genau das
        signalisiert einer künftigen Reconciliation "Ausgang unklar".
        """

        existing = self._repository.get(order.client_order_id)
        if existing is not None:
            return self._result_for_existing(existing, order)

        self._repository.save(
            OrderRecord(
                client_order_id=order.client_order_id,
                order=order,
                status=OrderStatus.CREATED,
            )
        )
        self._repository.save(
            OrderRecord(
                client_order_id=order.client_order_id,
                order=order,
                status=OrderStatus.SUBMITTED,
            )
        )

        execution_result = self._broker.execute(order)

        self._repository.save(
            OrderRecord(
                client_order_id=order.client_order_id,
                order=order,
                status=_EXECUTION_TO_ORDER_STATUS[execution_result.status],
                execution_result=execution_result,
            )
        )

        return execution_result

    def _result_for_existing(self, existing: OrderRecord, order: Order) -> ExecutionResult:
        if existing.execution_result is not None:
            return existing.execution_result

        return ExecutionResult(
            success=False,
            order=order,
            message=(
                f"Order {order.client_order_id} bereits bekannt "
                f"(Status {existing.status.value}), Ausgang unklar - "
                "keine erneute Broker-Ausführung."
            ),
            fee=0.0,
            slippage=0.0,
            status=ExecutionStatus.UNKNOWN,
            broker_order_id=None,
        )
