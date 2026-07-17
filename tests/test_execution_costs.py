from datetime import UTC, datetime

import pytest

from tradingbot.backtest.engine import BacktestEngine
from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import PaperBroker
from tradingbot.execution.models import Order
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.buy_and_hold import BuyAndHoldStrategy
from tradingbot.strategy.models import TradingSignal


class _AlwaysBuyStrategy(Strategy):
    """Test-Doppel, das immer ein BUY-Signal mit hoher Konfidenz liefert."""

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        return TradingSignal(symbol=symbol, signal="BUY", confidence=1.0)


def _candles(price: float = 100.0, symbol: str = "BTCUSDT", count: int = 2):

    now = datetime.now(UTC)
    return [
        MarketCandle(
            symbol=symbol,
            timestamp=now,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000,
        )
        for _ in range(count)
    ]


# --- PaperBroker: reine Berechnung ------------------------------------------------


def test_zero_cost_behaves_like_before():

    broker = PaperBroker()  # Standard: fee_percent=0.0, slippage_percent=0.0
    order = Order(symbol="BTCUSDT", side="BUY", quantity=0.1, price=60000)

    result = broker.execute(order)

    assert result.success is True
    assert result.fee == 0.0
    assert result.slippage == 0.0
    assert result.order.price == 60000


def test_fee_calculation_is_correct():

    broker = PaperBroker(fee_percent=0.01)  # 1 %
    order = Order(symbol="BTCUSDT", side="BUY", quantity=1.0, price=1000.0)

    result = broker.execute(order)

    # Kein Slippage -> Fill-Preis = 1000, Gebuehr = 1000 * 1 * 0.01 = 10
    assert result.fee == pytest.approx(10.0)


def test_slippage_increases_buy_fill_price():

    broker = PaperBroker(slippage_percent=0.02)  # 2 %
    order = Order(symbol="BTCUSDT", side="BUY", quantity=1.0, price=1000.0)

    result = broker.execute(order)

    assert result.order.price == pytest.approx(1020.0)
    assert result.slippage == pytest.approx(20.0)


def test_slippage_decreases_sell_fill_price():

    broker = PaperBroker(slippage_percent=0.02)
    order = Order(symbol="BTCUSDT", side="SELL", quantity=1.0, price=1000.0)

    result = broker.execute(order)

    assert result.order.price == pytest.approx(980.0)
    assert result.slippage == pytest.approx(20.0)


def test_execution_result_contains_costs():

    broker = PaperBroker(fee_percent=0.005, slippage_percent=0.01)
    order = Order(symbol="BTCUSDT", side="BUY", quantity=2.0, price=100.0)

    result = broker.execute(order)

    expected_fill_price = 100.0 * 1.01
    expected_slippage = abs(expected_fill_price - 100.0) * 2.0
    expected_fee = expected_fill_price * 2.0 * 0.005

    assert result.slippage == pytest.approx(expected_slippage)
    assert result.fee == pytest.approx(expected_fee)


# --- Orchestrator: Portfolio bucht effektiven Wert --------------------------------


def _build_orchestrator(
    initial_capital: float,
    max_position_size: float,
    fee_percent: float = 0.0,
    slippage_percent: float = 0.0,
):

    engine = TradingEngine()
    engine.start()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=_AlwaysBuyStrategy(),
        risk_manager=RiskManager(max_position_size=max_position_size),
        portfolio=portfolio,
        broker=PaperBroker(fee_percent=fee_percent, slippage_percent=slippage_percent),
    )
    return portfolio, orchestrator


def test_orchestrator_books_effective_value_including_fee_and_slippage():

    portfolio, orchestrator = _build_orchestrator(
        initial_capital=10000.0,
        max_position_size=1000.0,
        fee_percent=0.01,
        slippage_percent=0.02,
    )

    result = orchestrator.run_cycle(_candles(price=100.0))

    assert result.execution is not None
    assert result.execution.success is True

    fill_price = 100.0 * 1.02  # Slippage beim Kauf erhoeht den Preis
    quantity = 1000.0 / 100.0  # position_size / urspruenglicher Referenzpreis
    expected_cost = fill_price * quantity * 1.01  # inkl. 1 % Gebuehr

    assert portfolio.available_cash() == pytest.approx(10000.0 - expected_cost)


def test_cash_check_accounts_for_fee_and_slippage():

    # Ohne Kosten waere die Order (quantity=10 * price=100 = 1000) genau
    # leistbar. Mit Slippage+Gebuehr uebersteigt der tatsaechliche Bedarf das
    # verfuegbare Kapital, die Order muss abgelehnt werden.
    portfolio, orchestrator = _build_orchestrator(
        initial_capital=1000.0,
        max_position_size=1000.0,
        fee_percent=0.01,
        slippage_percent=0.02,
    )

    result = orchestrator.run_cycle(_candles(price=100.0))

    assert result.order is None
    assert result.execution is None
    assert portfolio.available_cash() == 1000.0


def test_capital_never_goes_negative_with_costs_enabled():

    portfolio, orchestrator = _build_orchestrator(
        initial_capital=150.0,
        max_position_size=100.0,
        fee_percent=0.05,
        slippage_percent=0.05,
    )

    for _ in range(5):
        orchestrator.run_cycle(_candles(price=100.0))
        assert portfolio.available_cash() >= 0.0


# --- Backtest bleibt kompatibel ----------------------------------------------------


def test_backtest_remains_compatible_with_cost_aware_broker():

    from tradingbot.data.simulated_provider import SimulatedDataProvider

    engine = TradingEngine()
    engine.start()
    portfolio = PortfolioManager(initial_capital=10000.0)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=BuyAndHoldStrategy(symbol="BTCUSDT"),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=PaperBroker(fee_percent=0.001, slippage_percent=0.001),
    )
    candles = SimulatedDataProvider(seed=4).get_candles(
        symbol="BTCUSDT", timeframe="1h", limit=10
    )

    backtest = BacktestEngine(
        orchestrator=orchestrator,
        portfolio=portfolio,
        symbol="BTCUSDT",
        candles=candles,
    )

    result = backtest.run()

    assert len(result.cycle_results) == len(candles) - 1
    assert result.trades == 1
    assert portfolio.available_cash() >= 0.0
