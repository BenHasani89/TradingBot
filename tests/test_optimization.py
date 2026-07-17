import statistics
from datetime import UTC, datetime

import pytest

from tradingbot.backtest.models import BacktestResult, EquityPoint
from tradingbot.backtest.optimization import rank_strategies
from tradingbot.backtest.parameter_grid import build_strategy_variants
from tradingbot.backtest.research import BacktestResearchRunner
from tradingbot.core.models import TradingCycleResult
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.portfolio.models import ClosedTrade
from tradingbot.risk.models import RiskDecision
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy


def _cycle_result_with_trade(closed_trade: ClosedTrade | None) -> TradingCycleResult:

    return TradingCycleResult(
        signal=TradingSignal(symbol="BTC", signal="SELL", confidence=1.0),
        decision=RiskDecision(approved=True, position_size=100.0, reason="ok"),
        order=None,
        execution=None,
        closed_trade=closed_trade,
    )


def _closed_trade(profit_loss: float, entry_price: float = 100.0, quantity: float = 1.0):

    return ClosedTrade(
        symbol="BTC",
        quantity=quantity,
        entry_price=entry_price,
        exit_price=entry_price + profit_loss / quantity,
        profit_loss=profit_loss,
    )


def _equity_curve(values: list[float]):

    now = datetime.now(UTC)
    return [EquityPoint(timestamp=now, total_value=v) for v in values]


def _build_result():
    """1 Jahr (4 Perioden, periods_per_year=4), 3 abgeschlossene Trades
    (2 Gewinne, 1 Verlust) plus ein Zyklus ohne abgeschlossenen Trade.
    """

    values = [1000.0, 1100.0, 990.0, 1210.0]
    equity_curve = _equity_curve(values)

    cycle_results = [
        _cycle_result_with_trade(_closed_trade(50.0)),
        _cycle_result_with_trade(_closed_trade(-20.0)),
        _cycle_result_with_trade(_closed_trade(30.0)),
        _cycle_result_with_trade(None),
    ]

    result = BacktestResult(
        trades=4,
        profit_loss=210.0,
        performance_percent=21.0,
        max_drawdown_percent=10.0,
        equity_curve=equity_curve,
        cycle_results=cycle_results,
    )
    return result, values


def test_rank_strategies_computes_all_fields_correctly():

    result, values = _build_result()

    ranked = rank_strategies({"Strategie A": result}, periods_per_year=4)

    assert len(ranked) == 1
    row = ranked[0]

    returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
    expected_sharpe = statistics.mean(returns) / statistics.stdev(returns) * (4**0.5)
    expected_volatility = statistics.stdev(returns) * (4**0.5) * 100

    assert row.strategy_name == "Strategie A"
    assert row.performance_percent == pytest.approx(21.0)
    # 1 Jahr -> Gesamtrendite entspricht der annualisierten Rendite.
    assert row.annualized_return_percent == pytest.approx(21.0)
    assert row.sharpe_ratio == pytest.approx(expected_sharpe)
    assert row.volatility_percent == pytest.approx(expected_volatility)
    assert row.max_drawdown_percent == pytest.approx(10.0)
    assert row.calmar_ratio == pytest.approx(2.1)
    # Abgeschlossene Trades (3), NICHT result.trades (4 Order-Ausfuehrungen).
    assert row.trades == 3
    assert row.win_rate_percent == pytest.approx(200 / 3)
    assert row.profit_factor == pytest.approx(80.0 / 20.0)
    assert row.average_trade == pytest.approx(20.0)
    assert row.payoff_ratio == pytest.approx(2.0)


def test_rank_strategies_sorts_descending_by_default_sharpe_ratio():

    result_good, _ = _build_result()

    result_bad = BacktestResult(
        trades=0,
        profit_loss=-150.0,
        performance_percent=-15.0,
        max_drawdown_percent=15.0,
        equity_curve=_equity_curve([1000.0, 950.0, 900.0, 850.0]),
        cycle_results=[],
    )

    ranked = rank_strategies({"Schlecht": result_bad, "Gut": result_good}, periods_per_year=4)

    assert [row.strategy_name for row in ranked] == ["Gut", "Schlecht"]


def test_rank_strategies_sorts_by_custom_metric():

    result_high_return, _ = _build_result()

    result_low_return = BacktestResult(
        trades=0,
        profit_loss=10.0,
        performance_percent=1.0,
        max_drawdown_percent=0.0,
        equity_curve=_equity_curve([1000.0, 1010.0]),
        cycle_results=[],
    )

    ranked = rank_strategies(
        {"Hoch": result_high_return, "Niedrig": result_low_return},
        periods_per_year=4,
        sort_by="performance_percent",
    )

    assert [row.strategy_name for row in ranked] == ["Hoch", "Niedrig"]


def test_rank_strategies_empty_results_returns_empty_list():

    assert rank_strategies({}, periods_per_year=252) == []


def test_rank_strategies_invalid_sort_by_raises():

    result, _ = _build_result()

    with pytest.raises(AttributeError):
        rank_strategies({"A": result}, periods_per_year=4, sort_by="not_a_field")


def test_full_optimization_pipeline_end_to_end():

    candles = SimulatedDataProvider(seed=2).get_candles(
        symbol="BTCUSDT", timeframe="1h", limit=30
    )
    variants = build_strategy_variants(
        MovingAverageCrossoverStrategy,
        {"short_window": [2, 3], "long_window": [5, 10]},
    )
    runner = BacktestResearchRunner(candles=candles, initial_capital=10000.0, risk_limit=1000.0)

    raw_results = runner.run_raw(variants)
    ranked = rank_strategies(raw_results, periods_per_year=24 * 365)

    assert len(raw_results) == 4
    assert len(ranked) == 4
    assert {row.strategy_name for row in ranked} == set(variants.keys())

    sharpe_values = [row.sharpe_ratio for row in ranked]
    assert sharpe_values == sorted(sharpe_values, reverse=True)
