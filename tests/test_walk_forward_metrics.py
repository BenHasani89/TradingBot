import statistics

import pytest

from tradingbot.backtest.optimization import RankedResult
from tradingbot.backtest.walk_forward import WalkForwardWindowResult
from tradingbot.backtest.walk_forward_metrics import (
    aggregate_walk_forward_results,
)


def _ranked_result(performance_percent: float, sharpe_ratio: float) -> RankedResult:

    return RankedResult(
        strategy_name="Test",
        performance_percent=performance_percent,
        annualized_return_percent=performance_percent,
        sharpe_ratio=sharpe_ratio,
        volatility_percent=0.0,
        max_drawdown_percent=0.0,
        calmar_ratio=0.0,
        trades=1,
        win_rate_percent=100.0,
        profit_factor=1.0,
        average_trade=1.0,
        payoff_ratio=1.0,
    )


def _window_result(index: int, performance_percent: float, sharpe_ratio: float):

    return WalkForwardWindowResult(
        window_index=index,
        winning_strategy_name="Test",
        in_sample_ranking=[_ranked_result(performance_percent, sharpe_ratio)],
        out_of_sample_result=_ranked_result(performance_percent, sharpe_ratio),
    )


def test_aggregate_walk_forward_results_computes_averages():

    results = [
        _window_result(0, performance_percent=10.0, sharpe_ratio=1.0),
        _window_result(1, performance_percent=-4.0, sharpe_ratio=-0.5),
        _window_result(2, performance_percent=6.0, sharpe_ratio=0.8),
    ]

    summary = aggregate_walk_forward_results(results)

    assert summary.window_count == 3
    assert summary.average_out_of_sample_performance_percent == pytest.approx(4.0)
    assert summary.average_out_of_sample_sharpe_ratio == pytest.approx((1.0 - 0.5 + 0.8) / 3)
    assert summary.performance_std_dev == pytest.approx(statistics.stdev([10.0, -4.0, 6.0]))
    # 2 von 3 Fenstern mit positiver Out-of-Sample-Performance.
    assert summary.profitable_window_ratio_percent == pytest.approx(200 / 3)


def test_aggregate_walk_forward_results_empty_list():

    summary = aggregate_walk_forward_results([])

    assert summary.window_count == 0
    assert summary.average_out_of_sample_performance_percent == 0.0
    assert summary.average_out_of_sample_sharpe_ratio == 0.0
    assert summary.performance_std_dev == 0.0
    assert summary.profitable_window_ratio_percent == 0.0


def test_aggregate_walk_forward_results_single_window_std_dev_is_zero():

    results = [_window_result(0, performance_percent=5.0, sharpe_ratio=1.0)]

    summary = aggregate_walk_forward_results(results)

    assert summary.window_count == 1
    assert summary.average_out_of_sample_performance_percent == pytest.approx(5.0)
    assert summary.performance_std_dev == 0.0
    assert summary.profitable_window_ratio_percent == pytest.approx(100.0)


def test_aggregate_walk_forward_results_all_windows_unprofitable():

    results = [
        _window_result(0, performance_percent=-5.0, sharpe_ratio=-1.0),
        _window_result(1, performance_percent=-2.0, sharpe_ratio=-0.3),
    ]

    summary = aggregate_walk_forward_results(results)

    assert summary.profitable_window_ratio_percent == 0.0
