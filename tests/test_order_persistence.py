import sqlite3
from datetime import UTC, datetime

from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_repository import OrderRecord, OrderRepository
from tradingbot.execution.persistence import SqliteOrderRepository

_NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)

_OLD_ORDER_RECORD_SCHEMA = """
CREATE TABLE order_record (
    client_order_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    execution_success INTEGER,
    execution_message TEXT,
    execution_fee REAL,
    execution_slippage REAL,
    execution_status TEXT,
    execution_broker_order_id TEXT,
    execution_filled_quantity REAL
)
"""


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


def test_save_and_get_roundtrip_persists_fee_asset(tmp_path):

    repository = _repository(tmp_path)
    order = _order()
    execution_result = ExecutionResult(
        success=True,
        order=order,
        message="Binance: Order-Status FILLED",
        fee=0.000001,
        slippage=0.0,
        status=ExecutionStatus.SUCCESS,
        broker_order_id="order-1",
        filled_quantity=0.1,
        fee_asset="BTC",
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

    assert loaded.execution_result.fee_asset == "BTC"


def test_save_and_get_roundtrip_without_fee_asset_stays_none(tmp_path):
    """Legacy-Fall (PaperBroker/MockLiveBroker, oder mehrere Fills mit
    unterschiedlichen commissionAsset-Werten) - fee_asset bleibt None."""

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

    assert loaded.execution_result.fee_asset is None


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


# --- Schema-Migration (order_record) --------------------------------------------------------


def test_save_and_get_work_after_migrating_a_pre_existing_old_schema_database(tmp_path):
    """Simuliert exakt den real aufgetretenen Fall: eine bereits
    existierende Datei mit dem ursprünglichen order_record-Schema (ohne
    execution_price/execution_fee_asset) muss nach Konstruktion von
    SqliteOrderRepository wieder normal nutzbar sein - inklusive
    vorher bereits vorhandener Zeilen."""

    db_path = str(tmp_path / "legacy.sqlite3")

    connection = sqlite3.connect(db_path)
    connection.execute(_OLD_ORDER_RECORD_SCHEMA)
    connection.execute(
        "INSERT INTO order_record ("
        "client_order_id, symbol, side, quantity, price, status, created_at, updated_at, "
        "execution_success, execution_message, execution_fee, execution_slippage, "
        "execution_status, execution_broker_order_id, execution_filled_quantity"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "legacy-order-1",
            "BTCUSDT",
            "BUY",
            0.1,
            60000.0,
            OrderStatus.FILLED.value,
            _NOW.isoformat(),
            _NOW.isoformat(),
            1,
            "Binance: Order-Status FILLED",
            0.0,
            0.0,
            ExecutionStatus.SUCCESS.value,
            "42",
            0.1,
        ),
    )
    connection.commit()
    connection.close()

    # Konstruktion gegen die bereits existierende, alte Datei - muss die
    # Migration transparent anwenden, nicht mit OperationalError scheitern.
    repository = SqliteOrderRepository(db_path)

    legacy_record = repository.get("legacy-order-1")
    assert legacy_record is not None
    assert legacy_record.status == OrderStatus.FILLED
    assert legacy_record.execution_result.filled_quantity == 0.1
    # Alte Zeile hatte kein execution_price/execution_fee_asset - fällt
    # sauber auf den Intent-Preis bzw. None zurück (siehe persistence.py).
    assert legacy_record.execution_result.order.price == 60000.0
    assert legacy_record.execution_result.fee_asset is None

    new_order = _order("new-order-1")
    execution_result = ExecutionResult(
        success=True,
        order=Order(
            symbol=new_order.symbol,
            side=new_order.side,
            quantity=new_order.quantity,
            price=60050.0,
            client_order_id=new_order.client_order_id,
        ),
        message="Binance: Order-Status FILLED",
        fee=0.000001,
        slippage=0.0,
        status=ExecutionStatus.SUCCESS,
        broker_order_id="new-order-1",
        filled_quantity=0.1,
        fee_asset="BTC",
    )
    repository.save(
        OrderRecord(
            client_order_id="new-order-1",
            order=new_order,
            status=OrderStatus.FILLED,
            created_at=_NOW,
            updated_at=_NOW,
            execution_result=execution_result,
        )
    )

    new_record = repository.get("new-order-1")
    assert new_record.execution_result.order.price == 60050.0
    assert new_record.execution_result.fee_asset == "BTC"

    assert {r.client_order_id for r in repository.all()} == {"legacy-order-1", "new-order-1"}
