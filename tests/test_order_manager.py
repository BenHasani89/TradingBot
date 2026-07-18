from datetime import UTC, datetime

import pytest

from tradingbot.execution.broker import Broker
from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_manager import OrderManager
from tradingbot.execution.order_repository import InMemoryOrderRepository, OrderRecord

_NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)


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
            client_order_id=order.client_order_id,
            order=order,
            status=OrderStatus.SUBMITTED,
            created_at=_NOW,
            updated_at=_NOW,
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


# --- Zeitstempel (created_at/updated_at) ---------------------------------------------------


class _Clock:

    def __init__(self, current: datetime):
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def test_submit_sets_created_at_and_updated_at_from_injected_clock():

    clock = _Clock(_NOW)
    broker = _FixedResultBroker(_success_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository, now=clock)
    order = _order()

    manager.submit(order)

    record = repository.get(order.client_order_id)
    assert record.created_at == _NOW
    assert record.updated_at == _NOW


def test_created_at_stays_stable_while_updated_at_advances_within_one_submit():

    clock = _Clock(_NOW)
    broker = _FixedResultBroker(_success_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository, now=clock)
    order = _order()

    later = datetime(2026, 7, 18, 12, 5, tzinfo=UTC)

    def _advancing_broker_execute(order: Order) -> ExecutionResult:
        clock.current = later
        return _success_result(order)

    broker.execute = _advancing_broker_execute  # simuliert Zeitverlauf während des Broker-Aufrufs

    manager.submit(order)

    record = repository.get(order.client_order_id)
    assert record.created_at == _NOW
    assert record.updated_at == later


# --- Partial Fill ---------------------------------------------------------------------------


def _partial_fill_result(order: Order) -> ExecutionResult:

    return ExecutionResult(
        success=True,
        order=order,
        message="Teilweise gefüllt",
        fee=0.05,
        slippage=0.0,
        status=ExecutionStatus.SUCCESS,
        broker_order_id=order.client_order_id,
        filled_quantity=order.quantity * 0.4,
    )


def test_submit_partial_fill_persists_partially_filled_status():

    broker = _FixedResultBroker(_partial_fill_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    result = manager.submit(order)

    assert result.filled_quantity == pytest.approx(order.quantity * 0.4)
    record = repository.get(order.client_order_id)
    assert record.status == OrderStatus.PARTIALLY_FILLED


def test_submit_success_with_zero_filled_quantity_persists_failed_status():

    def _zero_fill_result(order: Order) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            order=order,
            message="Nichts gefüllt",
            fee=0.0,
            slippage=0.0,
            status=ExecutionStatus.SUCCESS,
            filled_quantity=0.0,
        )

    broker = _FixedResultBroker(_zero_fill_result)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    manager.submit(order)

    record = repository.get(order.client_order_id)
    assert record.status == OrderStatus.FAILED
