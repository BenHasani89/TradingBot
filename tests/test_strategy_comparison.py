import pytest

from tradingbot.backtest.comparison import ComparisonRow, compare_strategies
from tradingbot.backtest.engine import BacktestEngine
from tradingbot.backtest.models import BacktestResult
from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.execution.broker import PaperBroker
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.buy_and_hold import BuyAndHoldStrategy
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy


def _fake_result(trades, profit_loss, performance_percent, max_drawdown_percent):

    return BacktestResult(
        trades=trades,
        profit_loss=profit_loss,
        performance_percent=performance_percent,
        max_drawdown_percent=max_drawdown_percent,
        equity_curve=[],
        cycle_results=[],
    )


def test_compare_strategies_returns_row_per_strategy():

    results = {
        "Strategie A": _fake_result(3, 500.0, 5.0, 2.0),
        "Strategie B": _fake_result(1, -100.0, -1.0, 8.0),
    }

    rows = compare_strategies(results)

    assert len(rows) == 2
    assert rows[0] == ComparisonRow(
        strategy_name="Strategie A",
        trades=3,
        profit_loss=500.0,
        performance_percent=5.0,
        max_drawdown_percent=2.0,
    )
    assert rows[1].strategy_name == "Strategie B"
    assert rows[1].max_drawdown_percent == 8.0


def test_compare_strategies_preserves_input_order():

    results = {
        "Zweite": _fake_result(0, 0.0, 0.0, 0.0),
        "Erste": _fake_result(1, 1.0, 1.0, 1.0),
    }

    rows = compare_strategies(results)

    assert [row.strategy_name for row in rows] == ["Zweite", "Erste"]


def test_compare_strategies_empty_input_returns_empty_list():

    assert compare_strategies({}) == []


def _run_backtest(strategy, symbol="BTCUSDT", limit=20, seed=42, initial_capital=10000.0):

    engine = TradingEngine()
    engine.start()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=strategy,
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    candles = SimulatedDataProvider(seed=seed).get_candles(
        symbol=symbol, timeframe="1h", limit=limit
    )
    backtest = BacktestEngine(
        orchestrator=orchestrator,
        portfolio=portfolio,
        symbol=symbol,
        candles=candles,
    )
    return backtest.run()


def test_compare_strategies_across_real_backtests_on_identical_data():

    # Exakt derselbe Seed -> beide Strategien laufen auf denselben Kerzen.
    moving_average_result = _run_backtest(
        MovingAverageCrossoverStrategy(short_window=2, long_window=5), seed=7
    )
    buy_and_hold_result = _run_backtest(BuyAndHoldStrategy(symbol="BTCUSDT"), seed=7)

    rows = compare_strategies(
        {
            "MovingAverageCrossover": moving_average_result,
            "BuyAndHold": buy_and_hold_result,
        }
    )

    assert [row.strategy_name for row in rows] == ["MovingAverageCrossover", "BuyAndHold"]

    ma_row = rows[0]
    assert ma_row.trades == moving_average_result.trades
    assert ma_row.profit_loss == pytest.approx(moving_average_result.profit_loss)
    assert ma_row.performance_percent == pytest.approx(
        moving_average_result.performance_percent
    )
    assert ma_row.max_drawdown_percent == pytest.approx(
        moving_average_result.max_drawdown_percent
    )

    bh_row = rows[1]
    assert bh_row.trades == 1  # BuyAndHold kauft genau einmal
