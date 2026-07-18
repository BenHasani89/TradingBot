from datetime import UTC, datetime

import pytest

from tradingbot.backtest.models import BacktestResult, EquityPoint
from tradingbot.backtest.portfolio_construction_engine import PortfolioConstructionResult
from tradingbot.backtest.portfolio_engine import PortfolioBacktestResult
from tradingbot.backtest.research_report import (
    PortfolioBacktestDetails,
    PortfolioConstructionDetails,
    ResearchSourceType,
    StrategyBacktestDetails,
    compare_reports,
    from_backtest_result,
    from_portfolio_backtest_result,
    from_portfolio_construction_result,
    rank_reports,
)
from tradingbot.core.models import TradingCycleResult
from tradingbot.portfolio.models import ClosedTrade
from tradingbot.portfolio_construction.models import RebalancingEvent, RebalancingTrade
from tradingbot.risk.models import RiskDecision
from tradingbot.strategy.models import TradingSignal

_EQUITY_VALUES = [1000.0, 1100.0, 990.0, 1210.0]


def _cycle_result(closed_trade: ClosedTrade | None) -> TradingCycleResult:

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


def _equity_curve():

    now = datetime.now(UTC)
    return [EquityPoint(timestamp=now, total_value=v) for v in _EQUITY_VALUES]


def _backtest_result() -> BacktestResult:

    cycle_results = [
        _cycle_result(_closed_trade(50.0)),
        _cycle_result(_closed_trade(-20.0)),
        _cycle_result(_closed_trade(30.0)),
        _cycle_result(None),
    ]
    return BacktestResult(
        trades=4,
        profit_loss=210.0,
        performance_percent=21.0,
        max_drawdown_percent=10.0,
        equity_curve=_equity_curve(),
        cycle_results=cycle_results,
    )


def _portfolio_backtest_result() -> PortfolioBacktestResult:

    cycles_by_symbol = {
        "A": [_cycle_result(_closed_trade(50.0)), _cycle_result(None)],
        "B": [_cycle_result(_closed_trade(-20.0)), _cycle_result(_closed_trade(30.0))],
    }
    return PortfolioBacktestResult(
        trades=4,
        profit_loss=210.0,
        performance_percent=21.0,
        max_drawdown_percent=10.0,
        equity_curve=_equity_curve(),
        equity_curve_by_symbol={},
        cycle_results_by_symbol=cycles_by_symbol,
        allocation={"A": 500.0, "B": 500.0},
    )


def _portfolio_construction_result() -> PortfolioConstructionResult:

    now = datetime.now(UTC)
    events = [
        RebalancingEvent(
            step_index=1,
            timestamp=now,
            target_weights={"A": 0.5, "B": 0.5},
            trades=[
                RebalancingTrade(symbol="A", side="BUY", quantity=5.0, price=100.0),
                RebalancingTrade(symbol="B", side="BUY", quantity=5.0, price=100.0),
            ],
        ),
    ]
    return PortfolioConstructionResult(
        trades=2,
        profit_loss=210.0,
        performance_percent=21.0,
        max_drawdown_percent=10.0,
        equity_curve=_equity_curve(),
        equity_curve_by_symbol={},
        allocation_history=[
            {"A": 0.5, "B": 0.5},
            {"A": 0.5, "B": 0.5},
            {"A": 0.5, "B": 0.5},
        ],
        rebalancing_events=events,
    )


# --- from_backtest_result --------------------------------------------------------------


def test_from_backtest_result_builds_correct_report():

    report = from_backtest_result("Strategy A", _backtest_result(), periods_per_year=4)

    assert report.name == "Strategy A"
    assert report.source_type == ResearchSourceType.STRATEGY_BACKTEST
    assert report.profit_loss == pytest.approx(210.0)
    assert report.performance_percent == pytest.approx(21.0)
    assert report.annualized_return_percent == pytest.approx(21.0)
    assert report.max_drawdown_percent == pytest.approx(10.0)
    assert report.calmar_ratio == pytest.approx(2.1)

    assert isinstance(report.details, StrategyBacktestDetails)
    assert report.details.order_executions == 4
    assert report.details.closed_trades == 3
    assert report.details.win_rate_percent == pytest.approx(200 / 3)
    assert report.details.profit_factor == pytest.approx(80.0 / 20.0)


# --- from_portfolio_backtest_result -------------------------------------------------------


def test_from_portfolio_backtest_result_aggregates_across_assets():

    report = from_portfolio_backtest_result(
        "Multi", _portfolio_backtest_result(), periods_per_year=4
    )

    assert report.source_type == ResearchSourceType.PORTFOLIO_BACKTEST
    assert isinstance(report.details, PortfolioBacktestDetails)
    # 3 abgeschlossene Trades ueber beide Assets zusammen (2 bei A+B, 1 None).
    assert report.details.closed_trades == 3
    assert report.details.allocation == {"A": 500.0, "B": 500.0}


# --- from_portfolio_construction_result ---------------------------------------------------


def test_from_portfolio_construction_result_uses_rebalancing_details():

    report = from_portfolio_construction_result(
        "Rebalance", _portfolio_construction_result(), periods_per_year=4
    )

    assert report.source_type == ResearchSourceType.PORTFOLIO_CONSTRUCTION
    assert isinstance(report.details, PortfolioConstructionDetails)
    assert report.details.rebalancing_orders == 2
    assert report.details.rebalancing_count == 1
    # step_index=1 -> equity_curve[0]=1000, gehandeltes Volumen 1000 -> 100%.
    assert report.details.turnover_percent == pytest.approx(100.0)
    assert report.details.final_allocation == {"A": 0.5, "B": 0.5}


# --- compare_reports / rank_reports -------------------------------------------------------


def test_compare_reports_preserves_order():

    report_a = from_backtest_result("A", _backtest_result(), 4)
    report_b = from_portfolio_construction_result("B", _portfolio_construction_result(), 4)

    result = compare_reports([report_b, report_a])

    assert [r.name for r in result] == ["B", "A"]


def test_rank_reports_sorts_descending_by_default_sharpe():

    good = from_backtest_result("Good", _backtest_result(), 4)
    now = datetime.now(UTC)
    bad_result = BacktestResult(
        trades=0,
        profit_loss=-500.0,
        performance_percent=-50.0,
        max_drawdown_percent=50.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=v) for v in [1000, 800, 600, 500]],
        cycle_results=[],
    )
    bad = from_backtest_result("Bad", bad_result, 4)

    ranked = rank_reports([bad, good])

    assert [r.name for r in ranked] == ["Good", "Bad"]


def test_rank_reports_sorts_by_custom_metric():

    good = from_backtest_result("Good", _backtest_result(), 4)
    now = datetime.now(UTC)
    other_result = BacktestResult(
        trades=0,
        profit_loss=5.0,
        performance_percent=0.5,
        max_drawdown_percent=0.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=v) for v in [1000, 1005]],
        cycle_results=[],
    )
    other = from_backtest_result("Other", other_result, 4)

    ranked = rank_reports([other, good], sort_by="performance_percent")

    assert ranked[0].name == "Good"


def test_rank_reports_invalid_sort_by_raises():

    good = from_backtest_result("Good", _backtest_result(), 4)

    with pytest.raises(AttributeError):
        rank_reports([good], sort_by="not_a_field")


def test_rank_reports_mixes_all_three_source_types_fairly():

    strategy_report = from_backtest_result("StrategyOnly", _backtest_result(), periods_per_year=4)
    portfolio_report = from_portfolio_backtest_result(
        "MultiAssetStrategy", _portfolio_backtest_result(), periods_per_year=4
    )
    construction_report = from_portfolio_construction_result(
        "Rebalanced", _portfolio_construction_result(), periods_per_year=4
    )

    ranked = rank_reports([strategy_report, portfolio_report, construction_report])

    assert len(ranked) == 3
    assert {r.source_type for r in ranked} == {
        ResearchSourceType.STRATEGY_BACKTEST,
        ResearchSourceType.PORTFOLIO_BACKTEST,
        ResearchSourceType.PORTFOLIO_CONSTRUCTION,
    }
    # Alle drei Fixtures nutzen dieselbe Equity-Kurve -> identische Sharpe
    # Ratio, unabhaengig von der Quelle. Direkter Beweis der Quellen-
    # unabhaengigen Fairness des Vergleichs.
    assert len({r.sharpe_ratio for r in ranked}) == 1


# --- Integration mit einer echten Engine --------------------------------------------------


def test_from_backtest_result_with_real_engine():

    from tradingbot.backtest.engine import BacktestEngine
    from tradingbot.core.engine import TradingEngine
    from tradingbot.core.orchestrator import TradingOrchestrator
    from tradingbot.data.simulated_provider import SimulatedDataProvider
    from tradingbot.execution.broker import PaperBroker
    from tradingbot.portfolio.manager import PortfolioManager
    from tradingbot.risk.manager import RiskManager
    from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy

    engine = TradingEngine()
    engine.start()
    portfolio = PortfolioManager(initial_capital=10000.0)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=MovingAverageCrossoverStrategy(short_window=2, long_window=5),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    candles = SimulatedDataProvider(seed=1).get_candles(symbol="BTCUSDT", timeframe="1h", limit=20)
    backtest = BacktestEngine(
        orchestrator=orchestrator, portfolio=portfolio, symbol="BTCUSDT", candles=candles
    )
    result = backtest.run()

    report = from_backtest_result("RealRun", result, periods_per_year=24 * 365)

    assert report.name == "RealRun"
    assert report.equity_curve == result.equity_curve
    assert isinstance(report.details, StrategyBacktestDetails)
