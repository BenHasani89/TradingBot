from tradingbot.execution.broker import Broker, PaperBroker
from tradingbot.execution.models import ExecutionStatus, Order


def test_paper_broker_is_a_broker():

    assert isinstance(PaperBroker(), Broker)


def test_paper_broker_execution():

    broker = PaperBroker()

    order = Order(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.1,
        price=60000,
    )

    result = broker.execute(order)

    assert result.success is True
    assert len(broker.history()) == 1
    assert broker.history()[0].symbol == "BTCUSDT"


# --- client_order_id / broker_order_id / status -----------------------------------------


def test_order_generates_a_client_order_id_automatically():

    order = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)

    assert order.client_order_id
    assert len(order.client_order_id) == 36  # UUID4-Format


def test_two_orders_get_different_client_order_ids():

    first = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)
    second = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)

    assert first.client_order_id != second.client_order_id


def test_paper_broker_preserves_client_order_id_on_filled_order():

    broker = PaperBroker(slippage_percent=0.01)
    order = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)

    result = broker.execute(order)

    assert result.order.client_order_id == order.client_order_id


def test_paper_broker_sets_broker_order_id_equal_to_client_order_id():

    broker = PaperBroker()
    order = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)

    result = broker.execute(order)

    assert result.broker_order_id == order.client_order_id


def test_paper_broker_sets_status_success():

    broker = PaperBroker()
    order = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)

    result = broker.execute(order)

    assert result.status == ExecutionStatus.SUCCESS


def test_execution_status_has_exactly_three_values():

    assert {status.value for status in ExecutionStatus} == {"success", "failed", "unknown"}
