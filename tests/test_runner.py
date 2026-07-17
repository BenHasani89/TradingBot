import pytest

from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.core.runner import TradingBotRunner
from tradingbot.data.market import MarketDataStore
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.execution.broker import PaperBroker
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.simple import SimpleStrategy


def _build_runner(candle_limit: int = 5):

    engine = TradingEngine()
    store = MarketDataStore()
    portfolio = PortfolioManager(initial_capital=10000.0)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    runner = TradingBotRunner(
        engine=engine,
        provider=SimulatedDataProvider(seed=1),
        store=store,
        orchestrator=orchestrator,
        symbol="BTCUSDT",
        timeframe="1h",
        candle_limit=candle_limit,
    )
    return engine, store, portfolio, runner


def test_run_once_raises_when_engine_not_running():

    _, _, _, runner = _build_runner()

    with pytest.raises(RuntimeError):
        runner.run_once()


def test_run_once_stores_fetched_candles():

    engine, store, _, runner = _build_runner(candle_limit=5)
    engine.start()

    runner.run_once()

    assert len(store.latest("BTCUSDT", 5)) == 5
    assert all(c.symbol == "BTCUSDT" for c in store.all())


def test_run_once_returns_trading_cycle_result():

    engine, _, _, runner = _build_runner(candle_limit=5)
    engine.start()

    result = runner.run_once()

    assert result.signal.symbol == "BTCUSDT"
    assert result.decision is not None


def test_run_once_twice_accumulates_store_history():

    engine, store, _, runner = _build_runner(candle_limit=5)
    engine.start()

    runner.run_once()
    runner.run_once()

    assert len(store.all()) == 10
    assert len(store.latest("BTCUSDT", 5)) == 5
