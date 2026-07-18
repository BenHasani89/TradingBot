import pytest

from tradingbot.execution.broker import Broker
from tradingbot.execution.mock_broker import MockExecutionScenario, MockLiveBroker, MockOutcome
from tradingbot.execution.models import ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_manager import OrderManager
from tradingbot.execution.order_repository import InMemoryOrderRepository
from tradingbot.paper_trading.reconciliation import ReconciliationService


def _order(client_order_id: str = "order-1") -> Order:

    return Order(
        symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000.0, client_order_id=client_order_id
    )


def _fixed_scenario_broker(scenario: MockExecutionScenario) -> MockLiveBroker:

    return MockLiveBroker(scenario_provider=lambda order: scenario)


def test_mock_live_broker_is_a_broker():

    assert isinstance(_fixed_scenario_broker(MockExecutionScenario(MockOutcome.SUCCESS)), Broker)


# --- SUCCESS --------------------------------------------------------------------------------


def test_success_scenario_returns_successful_result():

    broker = _fixed_scenario_broker(MockExecutionScenario(MockOutcome.SUCCESS))
    order = _order()

    result = broker.execute(order)

    assert result.success is True
    assert result.status == ExecutionStatus.SUCCESS
    assert result.broker_order_id == order.client_order_id


# --- FAILED (Reject) --------------------------------------------------------------------------


def test_failed_scenario_returns_rejected_result():

    broker = _fixed_scenario_broker(MockExecutionScenario(MockOutcome.FAILED))
    order = _order()

    result = broker.execute(order)

    assert result.success is False
    assert result.status == ExecutionStatus.FAILED
    assert result.broker_order_id is None


# --- UNKNOWN --------------------------------------------------------------------------------


def test_unknown_scenario_returns_unknown_result():

    broker = _fixed_scenario_broker(MockExecutionScenario(MockOutcome.UNKNOWN))
    order = _order()

    result = broker.execute(order)

    assert result.success is False
    assert result.status == ExecutionStatus.UNKNOWN


# --- TIMEOUT --------------------------------------------------------------------------------


def test_timeout_scenario_raises_and_leaves_no_stored_result():

    broker = _fixed_scenario_broker(MockExecutionScenario(MockOutcome.TIMEOUT))
    order = _order()

    with pytest.raises(TimeoutError):
        broker.execute(order)

    assert broker.get_order_status(order.client_order_id) is None


# --- PARTIAL_FILL -----------------------------------------------------------------------------


def test_partial_fill_scenario_sets_filled_quantity():

    broker = _fixed_scenario_broker(
        MockExecutionScenario(MockOutcome.PARTIAL_FILL, filled_quantity=0.04)
    )
    order = _order()

    result = broker.execute(order)

    assert result.success is True
    assert result.status == ExecutionStatus.SUCCESS
    assert result.filled_quantity == 0.04


# --- get_order_status() ohne konfigurierte Sequenz ---------------------------------------------


def test_get_order_status_returns_none_for_unknown_order():

    broker = _fixed_scenario_broker(MockExecutionScenario(MockOutcome.SUCCESS))

    assert broker.get_order_status("unknown-id") is None


def test_get_order_status_matches_execute_result_without_sequence():

    broker = _fixed_scenario_broker(MockExecutionScenario(MockOutcome.SUCCESS))
    order = _order()

    executed = broker.execute(order)
    looked_up = broker.get_order_status(order.client_order_id)

    assert looked_up == executed


# --- Verspätete Statusänderung ------------------------------------------------------------


def test_delayed_status_change_progresses_through_sequence():

    scenario = MockExecutionScenario(
        MockOutcome.UNKNOWN,
        status_sequence=[ExecutionStatus.UNKNOWN, ExecutionStatus.UNKNOWN, ExecutionStatus.SUCCESS],
    )
    broker = _fixed_scenario_broker(scenario)
    order = _order()

    broker.execute(order)

    first = broker.get_order_status(order.client_order_id)
    second = broker.get_order_status(order.client_order_id)
    third = broker.get_order_status(order.client_order_id)
    fourth = broker.get_order_status(order.client_order_id)  # nach Sequenzende: bleibt stabil

    assert first.status == ExecutionStatus.UNKNOWN
    assert second.status == ExecutionStatus.UNKNOWN
    assert third.status == ExecutionStatus.SUCCESS
    assert fourth.status == ExecutionStatus.SUCCESS


def test_delayed_status_change_works_after_timeout():
    """Der Kernfall: execute() wirft (Timeout), aber eine spätere
    get_order_status()-Abfrage klärt den wahren Ausgang auf."""

    scenario = MockExecutionScenario(
        MockOutcome.TIMEOUT, status_sequence=[ExecutionStatus.SUCCESS]
    )
    broker = _fixed_scenario_broker(scenario)
    order = _order()

    with pytest.raises(TimeoutError):
        broker.execute(order)

    # Direkt nach dem Timeout: noch kein Ergebnis bekannt, da die Sequenz erst
    # beim ersten get_order_status()-Aufruf konsumiert wird.
    result = broker.get_order_status(order.client_order_id)

    assert result is not None
    assert result.status == ExecutionStatus.SUCCESS


# --- Szenario-Funktion wird pro Order individuell aufgerufen -------------------------------


def test_scenario_provider_is_called_per_order():

    def scenario_for(order: Order) -> MockExecutionScenario:
        if order.symbol == "BTCUSDT":
            return MockExecutionScenario(MockOutcome.SUCCESS)
        return MockExecutionScenario(MockOutcome.FAILED)

    broker = MockLiveBroker(scenario_provider=scenario_for)

    btc_result = broker.execute(_order("order-1"))
    eth_order = Order(symbol="ETHUSDT", side="SELL", quantity=1.0, price=3000.0)
    eth_result = broker.execute(eth_order)

    assert btc_result.success is True
    assert eth_result.success is False


# --- Volles Zusammenspiel: OrderManager + Reconciliation ------------------------------------


def test_full_circle_order_manager_and_reconciliation_detect_recovered_timeout():
    """OrderManager: Order hängt nach einem simulierten Timeout bei
    SUBMITTED fest. ReconciliationService erkennt anhand von
    get_order_status(), dass der Broker die Order tatsächlich erfolgreich
    ausgeführt hat - der Mismatch macht die veraltete lokale Aufzeichnung
    sichtbar."""

    scenario = MockExecutionScenario(
        MockOutcome.TIMEOUT, status_sequence=[ExecutionStatus.SUCCESS]
    )
    broker = _fixed_scenario_broker(scenario)
    repository = InMemoryOrderRepository()
    manager = OrderManager(broker=broker, repository=repository)
    order = _order()

    with pytest.raises(TimeoutError):
        manager.submit(order)

    record = repository.get(order.client_order_id)
    assert record.status == OrderStatus.SUBMITTED

    reconciliation = ReconciliationService(broker=broker, order_repository=repository)
    result = reconciliation.reconcile_order(order.client_order_id)

    assert result.matched is False
    assert result.local_status == OrderStatus.SUBMITTED
    assert result.broker_status == ExecutionStatus.SUCCESS
    assert "Abweichung" in result.reason
