from datetime import UTC, datetime

import pytest

from tradingbot.backtest.metrics import (
    calmar_ratio,
    sharpe_ratio,
    volatility_percent,
)
from tradingbot.backtest.models import EquityPoint
from tradingbot.backtest.portfolio_construction_engine import PortfolioConstructionResult
from tradingbot.backtest.portfolio_construction_optimization import (
    rank_portfolio_configurations,
)
from tradingbot.portfolio_construction.models import RebalancingEvent, RebalancingTrade


def _trade(symbol: str, side: str, quantity: float, price: float) -> RebalancingTrade:

    return RebalancingTrade(symbol=symbol, side=side, quantity=quantity, price=price)


def _build_result():
    """1 Jahr (4 Perioden, periods_per_year=4), zwei Rebalancing-Ereignisse."""

    now = datetime.now(UTC)
    values = [1000.0, 1100.0, 990.0, 1210.0]
    equity_curve = [EquityPoint(timestamp=now, total_value=v) for v in values]

    events = [
        RebalancingEvent(
            step_index=1,
            timestamp=now,
            target_weights={"A": 0.5, "B": 0.5},
            trades=[
                _trade("A", "BUY", 5.0, 100.0),
                _trade("B", "BUY", 5.0, 100.0),
            ],
        ),
        RebalancingEvent(
            step_index=3,
            timestamp=now,
            target_weights={"A": 0.5, "B": 0.5},
            trades=[_trade("A", "SELL", 1.0, 100.0)],
        ),
    ]

    result = PortfolioConstructionResult(
        trades=3,
        profit_loss=210.0,
        performance_percent=21.0,
        max_drawdown_percent=10.0,
        equity_curve=equity_curve,
        equity_curve_by_symbol={},
        allocation_history=[],
        rebalancing_events=events,
    )
    return result, values


def test_rank_portfolio_configurations_computes_all_fields_correctly():

    result, values = _build_result()

    ranked = rank_portfolio_configurations({"Config A": result}, periods_per_year=4)

    assert len(ranked) == 1
    row = ranked[0]

    assert row.configuration_name == "Config A"
    assert row.performance_percent == pytest.approx(21.0)
    # 1 Jahr (4 Perioden bei periods_per_year=4) -> Gesamtrendite == annualisiert.
    assert row.annualized_return_percent == pytest.approx(21.0)
    assert row.max_drawdown_percent == pytest.approx(10.0)
    assert row.sharpe_ratio == pytest.approx(sharpe_ratio(result.equity_curve, 4))
    assert row.volatility_percent == pytest.approx(volatility_percent(result.equity_curve, 4))
    assert row.calmar_ratio == pytest.approx(calmar_ratio(result.equity_curve, 1000.0, 4))
    assert row.rebalancing_count == 2

    # Turnover: Ereignis 1 bei step_index=1 -> equity_curve[0]=1000, Handelsvolumen 1000 -> 100%.
    # Ereignis 2 bei step_index=3 -> equity_curve[2]=990, Handelsvolumen 100 -> 10.10...%.
    expected_turnover = (100.0 + (100.0 / 990.0 * 100)) / 2
    assert row.turnover_percent == pytest.approx(expected_turnover)


def test_rank_portfolio_configurations_no_rebalancing_events():

    now = datetime.now(UTC)
    result = PortfolioConstructionResult(
        trades=0,
        profit_loss=0.0,
        performance_percent=0.0,
        max_drawdown_percent=0.0,
        equity_curve=[
            EquityPoint(timestamp=now, total_value=1000.0),
            EquityPoint(timestamp=now, total_value=1000.0),
        ],
        equity_curve_by_symbol={},
        allocation_history=[],
        rebalancing_events=[],
    )

    ranked = rank_portfolio_configurations({"NoRebalance": result}, periods_per_year=252)

    assert ranked[0].rebalancing_count == 0
    assert ranked[0].turnover_percent == 0.0


def test_rank_portfolio_configurations_sorts_descending_by_default():

    result_good, _ = _build_result()
    now = datetime.now(UTC)
    result_bad = PortfolioConstructionResult(
        trades=0,
        profit_loss=-500.0,
        performance_percent=-50.0,
        max_drawdown_percent=50.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=v) for v in [1000, 800, 600, 500]],
        equity_curve_by_symbol={},
        allocation_history=[],
        rebalancing_events=[],
    )

    ranked = rank_portfolio_configurations(
        {"Schlecht": result_bad, "Gut": result_good}, periods_per_year=4
    )

    assert [row.configuration_name for row in ranked] == ["Gut", "Schlecht"]


def test_rank_portfolio_configurations_sorts_by_custom_metric():

    result, _ = _build_result()
    now = datetime.now(UTC)
    other = PortfolioConstructionResult(
        trades=0,
        profit_loss=5.0,
        performance_percent=0.5,
        max_drawdown_percent=0.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=v) for v in [1000, 1005]],
        equity_curve_by_symbol={},
        allocation_history=[],
        rebalancing_events=[],
    )

    ranked = rank_portfolio_configurations(
        {"Hoch": result, "Niedrig": other}, periods_per_year=4, sort_by="performance_percent"
    )

    assert ranked[0].configuration_name == "Hoch"


def test_rank_portfolio_configurations_empty_results_returns_empty_list():

    assert rank_portfolio_configurations({}, periods_per_year=252) == []


def test_rank_portfolio_configurations_invalid_sort_by_raises():

    result, _ = _build_result()

    with pytest.raises(AttributeError):
        rank_portfolio_configurations({"A": result}, periods_per_year=4, sort_by="not_a_field")
