from datetime import UTC, datetime

from tradingbot.backtest.models import EquityPoint
from tradingbot.backtest.portfolio_comparison import (
    PortfolioComparisonRow,
    compare_portfolio_configurations,
)
from tradingbot.backtest.portfolio_construction_engine import PortfolioConstructionResult


def _result(
    trades: int,
    profit_loss: float,
    performance_percent: float,
    max_drawdown_percent: float,
) -> PortfolioConstructionResult:

    now = datetime.now(UTC)
    return PortfolioConstructionResult(
        trades=trades,
        profit_loss=profit_loss,
        performance_percent=performance_percent,
        max_drawdown_percent=max_drawdown_percent,
        equity_curve=[EquityPoint(timestamp=now, total_value=1000.0 + profit_loss)],
        equity_curve_by_symbol={},
        allocation_history=[],
        rebalancing_events=[],
    )


def test_compare_portfolio_configurations_returns_row_per_configuration():

    results = {
        "Config A": _result(3, 500.0, 5.0, 2.0),
        "Config B": _result(1, -100.0, -1.0, 8.0),
    }

    rows = compare_portfolio_configurations(results)

    assert len(rows) == 2
    assert rows[0] == PortfolioComparisonRow(
        configuration_name="Config A",
        rebalancing_orders=3,
        profit_loss=500.0,
        performance_percent=5.0,
        max_drawdown_percent=2.0,
    )
    assert rows[1].configuration_name == "Config B"
    assert rows[1].rebalancing_orders == 1


def test_compare_portfolio_configurations_preserves_input_order():

    results = {
        "Zweite": _result(0, 0.0, 0.0, 0.0),
        "Erste": _result(1, 1.0, 1.0, 1.0),
    }

    rows = compare_portfolio_configurations(results)

    assert [row.configuration_name for row in rows] == ["Zweite", "Erste"]


def test_compare_portfolio_configurations_empty_input_returns_empty_list():

    assert compare_portfolio_configurations({}) == []
