import pytest

from tradingbot.execution.broker import Broker
from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_manager import OrderManager
from tradingbot.execution.order_repository import InMemoryOrderRepository, OrderRecord


class _FixedResultBroker(Broker):
    """Liefert bei jedem Aufruf ein fest konfiguriertes `ExecutionResult`
    und zählt die Aufrufe - macht Duplicate-Detection direkt beobachtbar."""

    def __init__(self, result_factory) -> None:
        self._result_factory = result_factory
        self.calls = 0

    def execute(self, order: Order) -> ExecutionResult:
        self.calls += 1
        return self._result_factory(order)

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        return None


class _FailingBroker(Broker):
    """Wirft bei jedem Aufruf - simuliert einen Broker-Fehler (z. B.
    Netzwerk-Timeout) mit unklarem Ausgang."""

    def execute(self, order: Order) -> ExecutionResult:
        raise ConnectionError("Broker nicht erreichbar")

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        return None


def _success_result(order: Order) -> ExecutionResult:

    return ExecutionResult(
        success=True,
        order=order,
        message="Paper Order ausgeführt",
        fee=0.5,
        slippage=0.0,
        status=ExecutionStatus.SUCCESS,
        broker_order_id=order.client_order_id,
    )


def _failed_result(order: Order) -> ExecutionResult:

    return ExecutionResult(
        success=False,
        order=order,
        message="Order abgelehnt",
        fee=0.0,
        slippage=0.0,
        status=ExecutionStatus.FAILED,
        broker_order_id=None,
    )


def _unknown_result(order: Order) -> ExecutionResult:

    return ExecutionResult(
        success=False,
        order=order,
        message="Zeitüberschreitung, Ausgang unklar",
        fee=0.0,
        slippage=0.0,
        status=ExecutionStatus.UNKNOWN,
        broker_order_id=None,
    )


def _order(client_order_id: str = "order-1") -> Order:

    return Order(
        symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000.0, client_order_id=client_order_id
    )


# --- Erfolgreicher Lifecycle ------------------------------------------------------------------


def test_submit_successful_order_returns_execution_result():

    broker = _FixedResultBroker(_success_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    result = manager.submit(order)

    assert result.success is True
    assert result.status == ExecutionStatus.SUCCESS
    assert broker.calls == 1


def test_submit_successful_order_persists_filled_status_and_result():

    broker = _FixedResultBroker(_success_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    manager.submit(order)

    record = repository.get(order.client_order_id)
    assert record is not None
    assert record.status == OrderStatus.FILLED
    assert record.execution_result is not None
    assert record.execution_result.success is True


# --- Fehlgeschlagene Order ---------------------------------------------------------------


def test_submit_failed_order_persists_failed_status():

    broker = _FixedResultBroker(_failed_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    result = manager.submit(order)

    assert result.success is False
    record = repository.get(order.client_order_id)
    assert record.status == OrderStatus.FAILED
    assert record.execution_result.success is False


# --- UNKNOWN-Status bleibt erhalten --------------------------------------------------------


def test_submit_unknown_execution_status_persists_unknown_order_status():

    broker = _FixedResultBroker(_unknown_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    result = manager.submit(order)

    assert result.status == ExecutionStatus.UNKNOWN
    record = repository.get(order.client_order_id)
    assert record.status == OrderStatus.UNKNOWN
    assert record.execution_result.status == ExecutionStatus.UNKNOWN


def test_broker_exception_leaves_record_at_submitted_without_execution_result():

    broker = _FailingBroker()
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    with pytest.raises(ConnectionError):
        manager.submit(order)

    record = repository.get(order.client_order_id)
    assert record is not None
    assert record.status == OrderStatus.SUBMITTED
    assert record.execution_result is None


# --- Duplicate Detection -------------------------------------------------------------------


def test_duplicate_client_order_id_does_not_call_broker_twice():

    broker = _FixedResultBroker(_success_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    first_result = manager.submit(order)
    second_result = manager.submit(order)

    assert broker.calls == 1
    assert second_result == first_result


def test_duplicate_with_no_execution_result_yet_returns_unknown_without_calling_broker():

    broker = _FixedResultBroker(_success_result)
    repository = InMemoryOrderRepository()
    order = _order()
    repository.save(
        OrderRecord(
            client_order_id=order.client_order_id, order=order, status=OrderStatus.SUBMITTED
        )
    )
    manager = OrderManager(broker=broker, repository=repository)

    result = manager.submit(order)

    assert broker.calls == 0
    assert result.status == ExecutionStatus.UNKNOWN
    assert result.success is False


def test_different_client_order_ids_both_execute():

    broker = _FixedResultBroker(_success_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)

    manager.submit(_order("order-1"))
    manager.submit(_order("order-2"))

    assert broker.calls == 2
    assert len(repository.all()) == 2
