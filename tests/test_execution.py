from tradingbot.execution.broker import Broker, PaperBroker
from tradingbot.execution.models import (
    ExecutionResult,
    ExecutionStatus,
    Order,
    OrderStatus,
    derive_order_status,
)


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


# --- get_order_status() ------------------------------------------------------------------


def test_get_order_status_returns_none_for_unknown_client_order_id():

    broker = PaperBroker()

    assert broker.get_order_status("unknown-id") is None


def test_get_order_status_returns_the_same_result_execute_returned():

    broker = PaperBroker(slippage_percent=0.01, fee_percent=0.005)
    order = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)

    executed = broker.execute(order)
    looked_up = broker.get_order_status(order.client_order_id)

    assert looked_up == executed


def test_get_order_status_is_independent_across_orders():

    broker = PaperBroker()
    first = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)
    second = Order(symbol="ETHUSDT", side="SELL", quantity=1.0, price=3000)

    broker.execute(first)

    assert broker.get_order_status(first.client_order_id) is not None
    assert broker.get_order_status(second.client_order_id) is None


# --- derive_order_status() ---------------------------------------------------------------


def _result(
    status: ExecutionStatus, filled_quantity: float | None, quantity: float = 1.0
) -> ExecutionResult:

    order = Order(symbol="BTCUSDT", side="BUY", quantity=quantity, price=100.0)
    return ExecutionResult(
        success=status == ExecutionStatus.SUCCESS,
        order=order,
        message="Test",
        fee=0.0,
        slippage=0.0,
        status=status,
        filled_quantity=filled_quantity,
    )


def test_derive_order_status_failed_ignores_filled_quantity():

    assert derive_order_status(_result(ExecutionStatus.FAILED, None)) == OrderStatus.FAILED
    assert derive_order_status(_result(ExecutionStatus.FAILED, 0.5)) == OrderStatus.FAILED


def test_derive_order_status_unknown_ignores_filled_quantity():

    assert derive_order_status(_result(ExecutionStatus.UNKNOWN, None)) == OrderStatus.UNKNOWN
    assert derive_order_status(_result(ExecutionStatus.UNKNOWN, 0.5)) == OrderStatus.UNKNOWN


def test_derive_order_status_success_with_none_is_legacy_filled():

    result = derive_order_status(_result(ExecutionStatus.SUCCESS, None))

    assert result == OrderStatus.FILLED


def test_derive_order_status_success_with_zero_filled_is_failed():

    result = derive_order_status(_result(ExecutionStatus.SUCCESS, 0.0, quantity=1.0))

    assert result == OrderStatus.FAILED


def test_derive_order_status_success_partial_fill():

    result = derive_order_status(_result(ExecutionStatus.SUCCESS, 0.4, quantity=1.0))

    assert result == OrderStatus.PARTIALLY_FILLED


def test_derive_order_status_success_full_fill():

    result = derive_order_status(_result(ExecutionStatus.SUCCESS, 1.0, quantity=1.0))

    assert result == OrderStatus.FILLED


def test_derive_order_status_success_overfill_is_still_filled():

    result = derive_order_status(_result(ExecutionStatus.SUCCESS, 1.2, quantity=1.0))

    assert result == OrderStatus.FILLED
