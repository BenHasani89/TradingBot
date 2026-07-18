from datetime import UTC, datetime

from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_repository import (
    InMemoryOrderRepository,
    OrderRecord,
    OrderRepository,
)

_NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)


def _order(client_order_id: str = "order-1") -> Order:

    return Order(
        symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000.0, client_order_id=client_order_id
    )


def _record(
    client_order_id: str = "order-1", status: OrderStatus = OrderStatus.CREATED
) -> OrderRecord:

    return OrderRecord(
        client_order_id=client_order_id,
        order=_order(client_order_id),
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_in_memory_repository_is_an_order_repository():

    assert isinstance(InMemoryOrderRepository(), OrderRepository)


def test_get_without_prior_save_returns_none():

    assert InMemoryOrderRepository().get("unknown") is None


def test_all_without_prior_save_returns_empty_list():

    assert InMemoryOrderRepository().all() == []


def test_save_and_get_roundtrip():

    repository = InMemoryOrderRepository()
    record = _record()

    repository.save(record)

    assert repository.get("order-1") == record


def test_save_overwrites_previous_record_for_same_client_order_id():

    repository = InMemoryOrderRepository()
    repository.save(_record(status=OrderStatus.CREATED))
    repository.save(_record(status=OrderStatus.SUBMITTED))

    loaded = repository.get("order-1")

    assert loaded.status == OrderStatus.SUBMITTED
    assert len(repository.all()) == 1


def test_save_carries_execution_result():

    repository = InMemoryOrderRepository()
    order = _order()
    execution_result = ExecutionResult(
        success=True,
        order=order,
        message="ok",
        fee=0.0,
        slippage=0.0,
        status=ExecutionStatus.SUCCESS,
        broker_order_id="order-1",
    )
    record = OrderRecord(
        client_order_id="order-1", order=order, status=OrderStatus.FILLED,
        created_at=_NOW, updated_at=_NOW,
        execution_result=execution_result,
    )

    repository.save(record)

    assert repository.get("order-1").execution_result == execution_result


def test_all_returns_every_saved_record():

    repository = InMemoryOrderRepository()
    repository.save(_record(client_order_id="order-1"))
    repository.save(_record(client_order_id="order-2"))

    assert {r.client_order_id for r in repository.all()} == {"order-1", "order-2"}
