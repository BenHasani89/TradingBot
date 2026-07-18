from datetime import UTC, datetime

from tradingbot.execution.broker import Broker
from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_repository import InMemoryOrderRepository, OrderRecord
from tradingbot.paper_trading.reconciliation import ReconciliationResult, ReconciliationService

_NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)


class _FakeStatusBroker(Broker):
    """Beantwortet `get_order_status()` aus einer fest vorgegebenen Zuordnung
    - `execute()` wird für Reconciliation-Tests nie aufgerufen."""

    def __init__(self, statuses: dict[str, ExecutionResult]) -> None:
        self._statuses = statuses

    def execute(self, order: Order) -> ExecutionResult:
        raise NotImplementedError("Reconciliation ruft execute() nie auf")

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        return self._statuses.get(client_order_id)


def _order(client_order_id: str = "order-1") -> Order:

    return Order(
        symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000.0, client_order_id=client_order_id
    )


def _local_record(client_order_id: str, status: OrderStatus) -> OrderRecord:

    return OrderRecord(
        client_order_id=client_order_id,
        order=_order(client_order_id),
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _broker_result(client_order_id: str, status: ExecutionStatus) -> ExecutionResult:

    return ExecutionResult(
        success=status == ExecutionStatus.SUCCESS,
        order=_order(client_order_id),
        message="Testergebnis",
        fee=0.0,
        slippage=0.0,
        status=status,
        broker_order_id=client_order_id if status == ExecutionStatus.SUCCESS else None,
    )


def _service(
    order_repository: InMemoryOrderRepository, broker_statuses: dict[str, ExecutionResult]
) -> ReconciliationService:

    return ReconciliationService(
        broker=_FakeStatusBroker(broker_statuses), order_repository=order_repository
    )


# --- Unbekannte Order ---------------------------------------------------------------------


def test_reconcile_order_unknown_locally_returns_unmatched_without_asking_broker():

    repository = InMemoryOrderRepository()
    service = _service(repository, broker_statuses={})

    result = service.reconcile_order("unknown-id")

    assert isinstance(result, ReconciliationResult)
    assert result.matched is False
    assert result.local_status is None
    assert result.broker_status is None
    assert "lokal nicht bekannt" in result.reason


# --- lokal FILLED + Broker SUCCESS -> matched ---------------------------------------------


def test_reconcile_order_local_filled_and_broker_success_matches():

    repository = InMemoryOrderRepository()
    repository.save(_local_record("order-1", OrderStatus.FILLED))
    service = _service(
        repository, broker_statuses={"order-1": _broker_result("order-1", ExecutionStatus.SUCCESS)}
    )

    result = service.reconcile_order("order-1")

    assert result.matched is True
    assert result.local_status == OrderStatus.FILLED
    assert result.broker_status == ExecutionStatus.SUCCESS


# --- lokal SUBMITTED + Broker SUCCESS -> Mismatch (der Kernfall) --------------------------


def test_reconcile_order_local_submitted_and_broker_success_is_mismatch():

    repository = InMemoryOrderRepository()
    repository.save(_local_record("order-1", OrderStatus.SUBMITTED))
    service = _service(
        repository, broker_statuses={"order-1": _broker_result("order-1", ExecutionStatus.SUCCESS)}
    )

    result = service.reconcile_order("order-1")

    assert result.matched is False
    assert result.local_status == OrderStatus.SUBMITTED
    assert result.broker_status == ExecutionStatus.SUCCESS
    assert "Abweichung" in result.reason


# --- lokal FILLED + Broker FAILED -> Mismatch ----------------------------------------------


def test_reconcile_order_local_filled_and_broker_failed_is_mismatch():

    repository = InMemoryOrderRepository()
    repository.save(_local_record("order-1", OrderStatus.FILLED))
    service = _service(
        repository, broker_statuses={"order-1": _broker_result("order-1", ExecutionStatus.FAILED)}
    )

    result = service.reconcile_order("order-1")

    assert result.matched is False
    assert result.local_status == OrderStatus.FILLED
    assert result.broker_status == ExecutionStatus.FAILED


# --- Broker kennt die Order nicht -----------------------------------------------------------


def test_reconcile_order_unknown_to_broker_is_mismatch():

    repository = InMemoryOrderRepository()
    repository.save(_local_record("order-1", OrderStatus.FILLED))
    service = _service(repository, broker_statuses={})

    result = service.reconcile_order("order-1")

    assert result.matched is False
    assert result.local_status == OrderStatus.FILLED
    assert result.broker_status is None
    assert "kennt diese Order nicht" in result.reason


# --- lokal UNKNOWN + Broker UNKNOWN -> konsistent, matched ----------------------------------


def test_reconcile_order_local_unknown_and_broker_unknown_matches():

    repository = InMemoryOrderRepository()
    repository.save(_local_record("order-1", OrderStatus.UNKNOWN))
    service = _service(
        repository, broker_statuses={"order-1": _broker_result("order-1", ExecutionStatus.UNKNOWN)}
    )

    result = service.reconcile_order("order-1")

    assert result.matched is True


# --- reconcile_all() ------------------------------------------------------------------------


def test_reconcile_all_covers_every_local_order():

    repository = InMemoryOrderRepository()
    repository.save(_local_record("order-1", OrderStatus.FILLED))
    repository.save(_local_record("order-2", OrderStatus.SUBMITTED))
    service = _service(
        repository,
        broker_statuses={
            "order-1": _broker_result("order-1", ExecutionStatus.SUCCESS),
            "order-2": _broker_result("order-2", ExecutionStatus.SUCCESS),
        },
    )

    results = service.reconcile_all()

    assert {r.client_order_id for r in results} == {"order-1", "order-2"}
    matched_by_id = {r.client_order_id: r.matched for r in results}
    assert matched_by_id["order-1"] is True
    assert matched_by_id["order-2"] is False


def test_reconcile_all_with_no_local_orders_returns_empty_list():

    service = _service(InMemoryOrderRepository(), broker_statuses={})

    assert service.reconcile_all() == []
