from datetime import UTC, datetime

import pytest

from tradingbot.backtest.models import BacktestResult, EquityPoint
from tradingbot.backtest.portfolio_construction_engine import PortfolioConstructionResult
from tradingbot.backtest.portfolio_engine import PortfolioBacktestResult
from tradingbot.backtest.utils import infer_initial_capital


def test_infer_initial_capital_reconstructs_correctly():

    now = datetime.now(UTC)
    result = BacktestResult(
        trades=0,
        profit_loss=200.0,
        performance_percent=20.0,
        max_drawdown_percent=0.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=1200.0)],
        cycle_results=[],
    )

    assert infer_initial_capital(result) == pytest.approx(1000.0)


def test_infer_initial_capital_empty_curve_is_zero():

    result = BacktestResult(
        trades=0,
        profit_loss=0.0,
        performance_percent=0.0,
        max_drawdown_percent=0.0,
        equity_curve=[],
        cycle_results=[],
    )

    assert infer_initial_capital(result) == 0.0


def test_infer_initial_capital_works_with_portfolio_backtest_result():

    now = datetime.now(UTC)
    result = PortfolioBacktestResult(
        trades=0,
        profit_loss=500.0,
        performance_percent=5.0,
        max_drawdown_percent=0.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=10500.0)],
        equity_curve_by_symbol={},
        cycle_results_by_symbol={},
        allocation={},
    )

    assert infer_initial_capital(result) == pytest.approx(10000.0)


def test_infer_initial_capital_works_with_portfolio_construction_result():

    now = datetime.now(UTC)
    result = PortfolioConstructionResult(
        trades=0,
        profit_loss=-100.0,
        performance_percent=-10.0,
        max_drawdown_percent=10.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=900.0)],
        equity_curve_by_symbol={},
        allocation_history=[],
        rebalancing_events=[],
    )

    assert infer_initial_capital(result) == pytest.approx(1000.0)
