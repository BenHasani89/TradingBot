from datetime import UTC, datetime, timedelta

from tradingbot.backtest.engine import BacktestEngine
from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.execution.broker import PaperBroker
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.buy_and_hold import BuyAndHoldStrategy
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy


def _flat_then_jump_candles(
    flat_price: float,
    jump_price: float,
    flat_count: int = 15,
    jump_count: int = 5,
    symbol: str = "BTCUSDT",
) -> list[MarketCandle]:

    now = datetime.now(UTC)
    candles: list[MarketCandle] = []

    for i in range(flat_count):
        candles.append(
            MarketCandle(
                symbol=symbol,
                timestamp=now + timedelta(hours=i),
                open=flat_price,
                high=flat_price,
                low=flat_price,
                close=flat_price,
                volume=1000,
            )
        )

    for i in range(jump_count):
        candles.append(
            MarketCandle(
                symbol=symbol,
                timestamp=now + timedelta(hours=flat_count + i),
                open=jump_price,
                high=jump_price,
                low=jump_price,
                close=jump_price,
                volume=1000,
            )
        )

    return candles


def test_moving_average_buy_when_short_above_long():

    strategy = MovingAverageCrossoverStrategy(short_window=5, long_window=20)
    candles = _flat_then_jump_candles(flat_price=100, jump_price=200)

    signal = strategy.analyze(candles)

    assert signal.signal == "BUY"
    assert signal.symbol == "BTCUSDT"
    assert 0.0 <= signal.confidence <= 1.0


def test_moving_average_sell_when_short_below_long():

    strategy = MovingAverageCrossoverStrategy(short_window=5, long_window=20)
    candles = _flat_then_jump_candles(flat_price=200, jump_price=100)

    signal = strategy.analyze(candles)

    assert signal.signal == "SELL"
    assert 0.0 <= signal.confidence <= 1.0


def test_moving_average_holds_with_insufficient_data():

    strategy = MovingAverageCrossoverStrategy(short_window=5, long_window=20)
    candles = _flat_then_jump_candles(
        flat_price=100, jump_price=200, flat_count=5, jump_count=4
    )  # nur 9 Kerzen, long_window=20

    signal = strategy.analyze(candles)

    assert signal.signal == "HOLD"
    assert signal.confidence == 0.0


def test_moving_average_holds_with_no_candles():

    strategy = MovingAverageCrossoverStrategy()

    signal = strategy.analyze([])

    assert signal.signal == "HOLD"
    assert signal.symbol == "UNKNOWN"


def test_moving_average_confidence_is_clamped_to_one():

    strategy = MovingAverageCrossoverStrategy(short_window=5, long_window=20)
    # Extremer Sprung: kurzer SMA um ein Vielfaches ueber dem langen SMA.
    candles = _flat_then_jump_candles(flat_price=10, jump_price=1000)

    signal = strategy.analyze(candles)

    assert signal.signal == "BUY"
    assert signal.confidence == 1.0


def test_buy_and_hold_buys_once_then_holds():

    strategy = BuyAndHoldStrategy(symbol="BTCUSDT")
    candles = _flat_then_jump_candles(flat_price=100, jump_price=100, flat_count=1, jump_count=0)

    first = strategy.analyze(candles)
    second = strategy.analyze(candles)
    third = strategy.analyze(candles)

    assert first.signal == "BUY"
    assert first.confidence == 1.0
    assert second.signal == "HOLD"
    assert third.signal == "HOLD"


def test_buy_and_hold_never_sells():

    strategy = BuyAndHoldStrategy(symbol="BTCUSDT")
    candles = _flat_then_jump_candles(flat_price=100, jump_price=50, flat_count=1, jump_count=1)

    signals = [strategy.analyze(candles).signal for _ in range(5)]

    assert "SELL" not in signals


def _build_orchestrator(strategy, initial_capital: float = 10000.0):

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=strategy,
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    return engine, portfolio, orchestrator


def test_moving_average_works_through_orchestrator():

    strategy = MovingAverageCrossoverStrategy(short_window=5, long_window=20)
    engine, portfolio, orchestrator = _build_orchestrator(strategy)
    engine.start()

    candles = _flat_then_jump_candles(flat_price=100, jump_price=200)
    result = orchestrator.run_cycle(candles)

    assert result.signal.signal == "BUY"
    assert result.decision.approved is True
    assert result.execution is not None
    assert result.execution.success is True
    assert len(portfolio.status().positions) == 1


def test_buy_and_hold_works_through_orchestrator():

    strategy = BuyAndHoldStrategy(symbol="BTCUSDT")
    engine, portfolio, orchestrator = _build_orchestrator(strategy)
    engine.start()

    candles = _flat_then_jump_candles(flat_price=100, jump_price=100, flat_count=1, jump_count=0)
    result = orchestrator.run_cycle(candles)

    assert result.signal.signal == "BUY"
    assert result.decision.approved is True
    assert len(portfolio.status().positions) == 1


def test_moving_average_works_through_backtest_engine():

    strategy = MovingAverageCrossoverStrategy(short_window=2, long_window=5)
    engine, portfolio, orchestrator = _build_orchestrator(strategy)
    engine.start()

    candles = SimulatedDataProvider(seed=11).get_candles(
        symbol="BTCUSDT", timeframe="1h", limit=20
    )
    backtest = BacktestEngine(
        orchestrator=orchestrator,
        portfolio=portfolio,
        symbol="BTCUSDT",
        candles=candles,
    )

    result = backtest.run()

    assert len(result.cycle_results) == len(candles) - 1
    assert len(result.equity_curve) == len(candles) - 1
    assert isinstance(result.trades, int)


def test_buy_and_hold_works_through_backtest_engine():

    strategy = BuyAndHoldStrategy(symbol="BTCUSDT")
    engine, portfolio, orchestrator = _build_orchestrator(strategy)
    engine.start()

    candles = SimulatedDataProvider(seed=11).get_candles(
        symbol="BTCUSDT", timeframe="1h", limit=10
    )
    backtest = BacktestEngine(
        orchestrator=orchestrator,
        portfolio=portfolio,
        symbol="BTCUSDT",
        candles=candles,
    )

    result = backtest.run()

    # BuyAndHold kauft genau einmal (beim ersten Zyklus), danach nur HOLD.
    assert result.trades == 1
