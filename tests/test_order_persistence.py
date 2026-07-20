from datetime import UTC, datetime

from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_repository import OrderRecord, OrderRepository
from tradingbot.execution.persistence import SqliteOrderRepository

_NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)


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
    record = OrderRecord(
        client_order_id="order-1",
        order=order,
        status=OrderStatus.SUBMITTED,
        created_at=_NOW,
        updated_at=_NOW,
    )

    repository.save(record)
    loaded = repository.get("order-1")

    assert loaded.client_order_id == "order-1"
    assert loaded.status == OrderStatus.SUBMITTED
    assert loaded.execution_result is None
    assert loaded.order.symbol == "BTCUSDT"
    assert loaded.created_at == _NOW
    assert loaded.updated_at == _NOW


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
        filled_quantity=0.05,
    )
    record = OrderRecord(
        client_order_id="order-1",
        order=order,
        status=OrderStatus.FILLED,
        created_at=_NOW,
        updated_at=_NOW,
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
    assert loaded.execution_result.filled_quantity == 0.05


def test_save_and_get_roundtrip_persists_real_execution_price_distinct_from_intent(tmp_path):
    """Kern des Audit-Consistency-Fixes auf Repository-Ebene: der echte
    Fill-Preis (execution_result.order.price) muss unabhängig vom
    Intent-Preis (order.price) gespeichert und beim Laden wieder auf
    execution_result.order.price abgebildet werden - nicht auf den
    Intent-Preis zurückfallen, solange execution_price vorhanden ist."""

    repository = _repository(tmp_path)
    order = _order()  # price=60000.0 (Intent)
    filled_order = Order(
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        price=60123.45,  # echter, abweichender Fill-Preis
        client_order_id=order.client_order_id,
    )
    execution_result = ExecutionResult(
        success=True,
        order=filled_order,
        message="Binance: Order-Status FILLED",
        fee=0.0,
        slippage=123.45 * 0.1,
        status=ExecutionStatus.SUCCESS,
        broker_order_id="order-1",
        filled_quantity=0.1,
    )
    record = OrderRecord(
        client_order_id="order-1",
        order=order,
        status=OrderStatus.FILLED,
        created_at=_NOW,
        updated_at=_NOW,
        execution_result=execution_result,
    )

    repository.save(record)
    loaded = repository.get("order-1")

    # Intent bleibt unverändert sichtbar:
    assert loaded.order.price == 60000.0
    # Execution zeigt den echten, abweichenden Fill-Preis:
    assert loaded.execution_result.order.price == 60123.45


def test_save_and_get_roundtrip_without_execution_price_falls_back_to_intent_price(tmp_path):
    """Legacy-Fall (z. B. PaperBroker/MockLiveBroker ohne abweichenden
    Fill-Preis): execution_result.order.price == order.price, entspricht
    weiterhin dem bisherigen Verhalten."""

    repository = _repository(tmp_path)
    order = _order()
    execution_result = ExecutionResult(
        success=True,
        order=order,
        message="Paper Order ausgeführt",
        fee=0.0,
        slippage=0.0,
        status=ExecutionStatus.SUCCESS,
        broker_order_id="order-1",
    )
    record = OrderRecord(
        client_order_id="order-1",
        order=order,
        status=OrderStatus.FILLED,
        created_at=_NOW,
        updated_at=_NOW,
        execution_result=execution_result,
    )

    repository.save(record)
    loaded = repository.get("order-1")

    assert loaded.execution_result.order.price == 60000.0


def test_save_overwrites_previous_record_for_same_client_order_id(tmp_path):

    repository = _repository(tmp_path)
    order = _order()
    repository.save(
        OrderRecord(
            client_order_id="order-1",
            order=order,
            status=OrderStatus.CREATED,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    repository.save(
        OrderRecord(
            client_order_id="order-1",
            order=order,
            status=OrderStatus.SUBMITTED,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )

    loaded = repository.get("order-1")

    assert loaded.status == OrderStatus.SUBMITTED
    assert len(repository.all()) == 1


def test_all_returns_every_saved_record_in_insertion_order(tmp_path):

    repository = _repository(tmp_path)
    repository.save(
        OrderRecord(
            client_order_id="order-1",
            order=_order("order-1"),
            status=OrderStatus.CREATED,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    repository.save(
        OrderRecord(
            client_order_id="order-2",
            order=_order("order-2"),
            status=OrderStatus.CREATED,
            created_at=_NOW,
            updated_at=_NOW,
        )
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
            client_order_id="order-1",
            order=order,
            status=OrderStatus.UNKNOWN,
            created_at=_NOW,
            updated_at=_NOW,
            execution_result=execution_result,
        )
    )

    loaded = repository.get("order-1")

    assert loaded.status == OrderStatus.UNKNOWN
    assert loaded.execution_result.status == ExecutionStatus.UNKNOWN
    assert loaded.execution_result.broker_order_id is None
