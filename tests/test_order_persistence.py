from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_repository import OrderRecord, OrderRepository
from tradingbot.execution.persistence import SqliteOrderRepository


def _repository(tmp_path) -> SqliteOrderRepository:

    return SqliteOrderRepository(str(tmp_path / "orders.sqlite3"))


def _order(client_order_id: str = "order-1") -> Order:

    return Order(
        symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000.0, client_order_id=client_order_id
    )


def test_sqlite_repository_is_an_order_repository(tmp_path):

    assert isinstance(_repository(tmp_path), OrderRepository)


def test_get_without_prior_save_returns_none(tmp_path):

    assert _repository(tmp_path).get("unknown") is None


def test_all_without_prior_save_returns_empty_list(tmp_path):

    assert _repository(tmp_path).all() == []


def test_save_and_get_roundtrip_without_execution_result(tmp_path):

    repository = _repository(tmp_path)
    order = _order()
    record = OrderRecord(client_order_id="order-1", order=order, status=OrderStatus.SUBMITTED)

    repository.save(record)
    loaded = repository.get("order-1")

    assert loaded.client_order_id == "order-1"
    assert loaded.status == OrderStatus.SUBMITTED
    assert loaded.execution_result is None
    assert loaded.order.symbol == "BTCUSDT"


def test_save_and_get_roundtrip_with_execution_result(tmp_path):

    repository = _repository(tmp_path)
    order = _order()
    execution_result = ExecutionResult(
        success=True,
        order=order,
        message="Paper Order ausgeführt",
        fee=1.5,
        slippage=0.5,
        status=ExecutionStatus.SUCCESS,
        broker_order_id="order-1",
    )
    record = OrderRecord(
        client_order_id="order-1", order=order, status=OrderStatus.FILLED,
        execution_result=execution_result,
    )

    repository.save(record)
    loaded = repository.get("order-1")

    assert loaded.status == OrderStatus.FILLED
    assert loaded.execution_result is not None
    assert loaded.execution_result.success is True
    assert loaded.execution_result.fee == 1.5
    assert loaded.execution_result.status == ExecutionStatus.SUCCESS
    assert loaded.execution_result.broker_order_id == "order-1"


def test_save_overwrites_previous_record_for_same_client_order_id(tmp_path):

    repository = _repository(tmp_path)
    order = _order()
    repository.save(
        OrderRecord(client_order_id="order-1", order=order, status=OrderStatus.CREATED)
    )
    repository.save(
        OrderRecord(client_order_id="order-1", order=order, status=OrderStatus.SUBMITTED)
    )

    loaded = repository.get("order-1")

    assert loaded.status == OrderStatus.SUBMITTED
    assert len(repository.all()) == 1


def test_all_returns_every_saved_record_in_insertion_order(tmp_path):

    repository = _repository(tmp_path)
    repository.save(
        OrderRecord(client_order_id="order-1", order=_order("order-1"), status=OrderStatus.CREATED)
    )
    repository.save(
        OrderRecord(client_order_id="order-2", order=_order("order-2"), status=OrderStatus.CREATED)
    )

    all_records = repository.all()

    assert [r.client_order_id for r in all_records] == ["order-1", "order-2"]


def test_records_unknown_status_execution_result(tmp_path):

    repository = _repository(tmp_path)
    order = _order()
    execution_result = ExecutionResult(
        success=False,
        order=order,
        message="Ausgang unklar",
        fee=0.0,
        slippage=0.0,
        status=ExecutionStatus.UNKNOWN,
        broker_order_id=None,
    )
    repository.save(
        OrderRecord(
            client_order_id="order-1", order=order, status=OrderStatus.UNKNOWN,
            execution_result=execution_result,
        )
    )

    loaded = repository.get("order-1")

    assert loaded.status == OrderStatus.UNKNOWN
    assert loaded.execution_result.status == ExecutionStatus.UNKNOWN
    assert loaded.execution_result.broker_order_id is None
