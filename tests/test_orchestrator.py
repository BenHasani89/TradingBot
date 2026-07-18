from datetime import UTC, datetime

import pytest

from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import Broker, PaperBroker
from tradingbot.execution.models import ExecutionResult, ExecutionStatus, Order, OrderStatus
from tradingbot.execution.order_repository import InMemoryOrderRepository
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.simple import SimpleStrategy


def _candles(previous_close: float, current_close: float, symbol: str = "BTCUSDT"):

    return [
        MarketCandle(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            open=previous_close,
            high=previous_close,
            low=previous_close,
            close=previous_close,
            volume=1000,
        ),
        MarketCandle(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            open=current_close,
            high=current_close,
            low=current_close,
            close=current_close,
            volume=1000,
        ),
    ]


def _build_orchestrator(initial_capital: float = 10000.0, max_position_size: float = 1000.0):

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=max_position_size),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    return engine, portfolio, orchestrator


def test_run_cycle_raises_when_engine_not_running():

    _, _, orchestrator = _build_orchestrator()

    with pytest.raises(RuntimeError):
        orchestrator.run_cycle(_candles(100, 110))


def test_run_cycle_executes_buy_and_updates_portfolio():

    engine, portfolio, orchestrator = _build_orchestrator(
        initial_capital=10000.0,
        max_position_size=1000.0,
    )
    engine.start()

    result = orchestrator.run_cycle(_candles(100, 110))

    assert result.signal.signal == "BUY"
    assert result.decision.approved is True
    assert result.order is not None
    assert result.order.side == "BUY"
    assert result.order.quantity == pytest.approx(1000.0 / 110.0)
    assert result.execution is not None
    assert result.execution.success is True

    status = portfolio.status()
    assert status.capital == pytest.approx(10000.0 - 1000.0)
    assert len(status.positions) == 1
    assert status.positions[0].symbol == "BTCUSDT"
    assert status.positions[0].quantity == pytest.approx(1000.0 / 110.0)


def test_run_cycle_does_not_trade_on_hold_signal():

    engine, portfolio, orchestrator = _build_orchestrator()
    engine.start()

    # Gleicher Schlusskurs -> SimpleStrategy liefert HOLD.
    result = orchestrator.run_cycle(_candles(100, 100))

    assert result.signal.signal == "HOLD"
    assert result.decision.approved is False
    assert result.order is None
    assert result.execution is None

    status = portfolio.status()
    assert status.capital == pytest.approx(10000.0)
    assert status.positions == []


# --- Order Management Layer: TradingOrchestrator ruft Broker über OrderManager auf ------------


def test_run_cycle_routes_execution_through_order_manager_without_double_invocation():

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=10000.0)
    broker = PaperBroker()
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=broker,
    )
    engine.start()

    result = orchestrator.run_cycle(_candles(100, 110))

    assert result.execution is not None
    assert result.order.client_order_id
    # Broker wurde über den OrderManager genau einmal aufgerufen, nicht doppelt.
    assert len(broker.history()) == 1
    assert broker.history()[0].client_order_id == result.order.client_order_id


# --- Option B: optionaler order_repository-Injection-Punkt ------------------------------------


def test_orchestrator_without_order_repository_uses_in_memory_default():
    """Bestehende Aufrufer (Backtest, ältere Tests) übergeben kein
    order_repository - das Verhalten muss identisch zum bisherigen Zustand
    bleiben (In-Memory, kein Dateipfad, keine Persistenz)."""

    engine, portfolio, orchestrator = _build_orchestrator()

    assert isinstance(orchestrator._order_manager._repository, InMemoryOrderRepository)


def test_orchestrator_uses_injected_order_repository():

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=10000.0)
    broker = PaperBroker()
    repository = InMemoryOrderRepository()
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=broker,
        order_repository=repository,
    )
    engine.start()

    result = orchestrator.run_cycle(_candles(100, 110))

    assert result.execution is not None
    record = repository.get(result.order.client_order_id)
    assert record is not None
    assert record.status == OrderStatus.FILLED
    assert record.execution_result.success is True


def test_orchestrator_uses_the_exact_injected_repository_instance_not_a_copy():

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=10000.0)
    injected_repository = InMemoryOrderRepository()
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=PaperBroker(),
        order_repository=injected_repository,
    )

    assert orchestrator._order_manager._repository is injected_repository


# --- Partial Fill: Portfolio-Buchung nutzt die tatsächlich gefüllte Menge --------------------


class _PartialFillBroker(Broker):
    """Füllt jede Order nur zu einem festen Anteil - simuliert einen
    echten Partial Fill unabhängig von einer konkreten Exchange."""

    def __init__(self, fill_ratio: float) -> None:
        self._fill_ratio = fill_ratio

    def execute(self, order: Order) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            order=order,
            message="Teilweise gefüllt",
            fee=0.0,
            slippage=0.0,
            status=ExecutionStatus.SUCCESS,
            broker_order_id=order.client_order_id,
            filled_quantity=order.quantity * self._fill_ratio,
        )

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        return None


class _ZeroFillBroker(Broker):
    """Meldet `success=False` bei `filled_quantity=0.0` - so muss ein
    Broker sich verhalten, damit `derive_order_status()`s FAILED-Fall und
    `ExecutionResult.success` konsistent bleiben (siehe
    `execution/live_broker.py`)."""

    def execute(self, order: Order) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            order=order,
            message="Nichts gefüllt",
            fee=0.0,
            slippage=0.0,
            status=ExecutionStatus.SUCCESS,
            filled_quantity=0.0,
        )

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        return None


def test_run_cycle_books_only_actually_filled_quantity_on_partial_fill():

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=10000.0)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=_PartialFillBroker(fill_ratio=0.4),
    )
    engine.start()

    result = orchestrator.run_cycle(_candles(100, 110))

    requested_quantity = 1000.0 / 110
    expected_filled = requested_quantity * 0.4

    assert result.execution.filled_quantity == pytest.approx(expected_filled)
    status = portfolio.status()
    assert len(status.positions) == 1
    assert status.positions[0].quantity == pytest.approx(expected_filled)
    # Kapital wird nur für die tatsächlich gefüllte Menge reduziert, nicht
    # für die ursprünglich angefragte.
    assert status.capital == pytest.approx(10000.0 - expected_filled * 110.0)


class _ContradictoryZeroFillBroker(Broker):
    """Verletzt bewusst den Vertrag `filled_quantity==0 => success=False`
    (z. B. eine denkbare Fehlkonfiguration eines künftigen Brokers) - dient
    ausschliesslich dazu, TradingOrchestrators Sicherheitsnetz gegen genau
    diesen Widerspruch zu prüfen (siehe core/orchestrator.py)."""

    def execute(self, order: Order) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            order=order,
            message="Widersprüchlich: success=True trotz filled_quantity=0",
            fee=0.0,
            slippage=0.0,
            status=ExecutionStatus.SUCCESS,
            broker_order_id=order.client_order_id,
            filled_quantity=0.0,
        )

    def get_order_status(self, client_order_id: str) -> ExecutionResult | None:
        return None


def test_run_cycle_does_not_divide_by_zero_when_broker_contradicts_itself():
    """success=True kombiniert mit filled_quantity=0.0 darf weder eine
    ZeroDivisionError auslösen noch einen Trade buchen - ein korrekter
    Broker sendet diese Kombination nie (siehe execution/live_broker.py),
    aber TradingOrchestrator darf sich nicht darauf verlassen."""

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=10000.0)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=_ContradictoryZeroFillBroker(),
    )
    engine.start()

    result = orchestrator.run_cycle(_candles(100, 110))

    assert result.execution.success is True
    assert result.closed_trade is None
    assert portfolio.status().positions == []
    assert portfolio.status().capital == pytest.approx(10000.0)


def test_run_cycle_does_not_book_when_nothing_was_filled():

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=10000.0)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=_ZeroFillBroker(),
    )
    engine.start()

    result = orchestrator.run_cycle(_candles(100, 110))

    assert result.execution.success is False
    assert portfolio.status().positions == []
    assert portfolio.status().capital == pytest.approx(10000.0)
