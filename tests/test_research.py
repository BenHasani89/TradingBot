import pytest

from tradingbot.backtest.research import BacktestResearchRunner
from tradingbot.data.models import MarketCandle
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.buy_and_hold import BuyAndHoldStrategy
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy


class _AlwaysHoldStrategy(Strategy):
    """Test-Doppel, das nie handelt - dient zur Prüfung der Zustandsisolation."""

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        return TradingSignal(symbol=symbol, signal="HOLD", confidence=0.0)


def _candles(seed: int, limit: int = 20, symbol: str = "BTCUSDT"):

    return SimulatedDataProvider(seed=seed).get_candles(
        symbol=symbol, timeframe="1h", limit=limit
    )


def test_research_runner_returns_correct_row_count():

    runner = BacktestResearchRunner(
        candles=_candles(seed=1, limit=10),
        initial_capital=10000.0,
        risk_limit=1000.0,
    )

    rows = runner.run(
        {
            "BuyAndHold": BuyAndHoldStrategy(symbol="BTCUSDT"),
            "MovingAverage": MovingAverageCrossoverStrategy(short_window=2, long_window=4),
            "AlwaysHold": _AlwaysHoldStrategy(),
        }
    )

    assert len(rows) == 3
    assert {row.strategy_name for row in rows} == {"BuyAndHold", "MovingAverage", "AlwaysHold"}


def test_research_runner_results_are_separated_per_strategy():

    runner = BacktestResearchRunner(
        candles=_candles(seed=3, limit=20),
        initial_capital=10000.0,
        risk_limit=1000.0,
    )

    rows = runner.run(
        {
            "BuyAndHold": BuyAndHoldStrategy(symbol="BTCUSDT"),
            "AlwaysHold": _AlwaysHoldStrategy(),
        }
    )

    by_name = {row.strategy_name: row for row in rows}
    assert by_name["BuyAndHold"].trades == 1
    assert by_name["AlwaysHold"].trades == 0


def test_research_runner_uses_identical_candles_for_all_strategies():

    runner = BacktestResearchRunner(
        candles=_candles(seed=9, limit=15),
        initial_capital=5000.0,
        risk_limit=500.0,
    )

    rows = runner.run(
        {
            "BuyAndHold1": BuyAndHoldStrategy(symbol="BTCUSDT"),
            "BuyAndHold2": BuyAndHoldStrategy(symbol="BTCUSDT"),
        }
    )

    # Identische Strategie-Logik auf denselben Kerzen -> identische Kennzahlen.
    assert rows[0].trades == rows[1].trades == 1
    assert rows[0].profit_loss == pytest.approx(rows[1].profit_loss)
    assert rows[0].performance_percent == pytest.approx(rows[1].performance_percent)
    assert rows[0].max_drawdown_percent == pytest.approx(rows[1].max_drawdown_percent)


def test_research_runner_does_not_share_portfolio_state_between_strategies():

    runner = BacktestResearchRunner(
        candles=_candles(seed=5, limit=20),
        initial_capital=10000.0,
        risk_limit=1000.0,
    )

    rows = runner.run(
        {
            "AktivMovingAverage": MovingAverageCrossoverStrategy(short_window=2, long_window=5),
            "ImmerHalten": _AlwaysHoldStrategy(),
        }
    )

    hold_row = next(row for row in rows if row.strategy_name == "ImmerHalten")

    # Wenn Portfolio-Zustand zwischen Strategien geteilt wuerde, haetten die
    # Trades der aktiven Strategie hier sichtbare Spuren hinterlassen.
    assert hold_row.trades == 0
    assert hold_row.profit_loss == 0.0
    assert hold_row.performance_percent == 0.0
    assert hold_row.max_drawdown_percent == 0.0
