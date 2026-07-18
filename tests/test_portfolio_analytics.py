from datetime import UTC, datetime

import pytest

from tradingbot.backtest.metrics import max_drawdown_percent, sharpe_ratio, volatility_percent
from tradingbot.backtest.models import EquityPoint
from tradingbot.backtest.portfolio_analytics import (
    asset_contribution_to_drawdown,
    asset_contribution_to_return,
    concentration_risk_over_time,
    exposure_over_time,
    risk_per_asset,
)
from tradingbot.backtest.portfolio_engine import PortfolioBacktestResult


def _result(
    equity_curve_by_symbol: dict[str, list[float]],
    allocation: dict[str, float],
) -> PortfolioBacktestResult:

    now = datetime.now(UTC)
    symbols = list(equity_curve_by_symbol.keys())
    per_symbol_curves = {
        symbol: [EquityPoint(timestamp=now, total_value=v) for v in values]
        for symbol, values in equity_curve_by_symbol.items()
    }
    step_count = len(next(iter(per_symbol_curves.values())))
    equity_curve = [
        EquityPoint(
            timestamp=now,
            total_value=sum(per_symbol_curves[symbol][t].total_value for symbol in symbols),
        )
        for t in range(step_count)
    ]

    return PortfolioBacktestResult(
        trades=0,
        profit_loss=equity_curve[-1].total_value - sum(allocation.values()),
        performance_percent=0.0,
        max_drawdown_percent=0.0,
        equity_curve=equity_curve,
        equity_curve_by_symbol=per_symbol_curves,
        cycle_results_by_symbol={symbol: [] for symbol in symbols},
        allocation=allocation,
    )


# --- asset_contribution_to_return -------------------------------------------------------


def test_asset_contribution_to_return_correct():

    result = _result(
        equity_curve_by_symbol={"A": [3000, 3200, 3500], "B": [3000, 2900, 2700]},
        allocation={"A": 3000.0, "B": 3000.0},
    )

    contributions = asset_contribution_to_return(result)

    assert contributions["A"] == pytest.approx(500.0)
    assert contributions["B"] == pytest.approx(-300.0)


def test_asset_contribution_to_return_captures_realized_profit_without_open_position():

    # Simuliert eine bereits vollstaendig geschlossene, profitable Position:
    # der Endwert (nur noch notionales Cash, keine offene Position mehr)
    # spiegelt den realisierten Gewinn bereits vollstaendig wider - keine
    # separate Addition von ClosedTrade-Werten noetig (keine Doppelzaehlung).
    result = _result(
        equity_curve_by_symbol={"A": [3000, 3200, 3500]},
        allocation={"A": 3000.0},
    )

    contributions = asset_contribution_to_return(result)

    assert contributions["A"] == pytest.approx(500.0)


# --- asset_contribution_to_drawdown -------------------------------------------------------


def test_asset_contribution_to_drawdown_relative_to_portfolio_drawdown():

    result = _result(
        equity_curve_by_symbol={
            "A": [1000, 1000, 700, 900],
            "B": [1000, 1000, 1000, 1000],
        },
        allocation={"A": 1000.0, "B": 1000.0},
    )
    # Portfolio: [2000, 2000, 1700, 1900] -> Peak=2000, Trough=1700, Betrag=300
    # A veraendert sich im selben Fenster um 300 -> 100 % Beitrag, B um 0 -> 0 %.

    contributions = asset_contribution_to_drawdown(result)

    assert contributions["A"] == pytest.approx(100.0)
    assert contributions["B"] == pytest.approx(0.0)


def test_asset_contribution_to_drawdown_can_be_negative_when_asset_offsets_decline():

    result = _result(
        equity_curve_by_symbol={
            "A": [1000, 1000, 500, 800],
            "B": [1000, 1000, 1200, 1000],
        },
        allocation={"A": 1000.0, "B": 1000.0},
    )
    # Portfolio: [2000, 2000, 1700, 1800] -> Peak=2000, Trough=1700, Betrag=300
    # A faellt um 500 (166.67 % Beitrag), B steigt um 200 (-66.67 % Beitrag) -
    # zusammen ergeben sie exakt die 100 % des Portfolio-Drawdowns.

    contributions = asset_contribution_to_drawdown(result)

    assert contributions["A"] == pytest.approx(500 / 300 * 100)
    assert contributions["B"] == pytest.approx(-200 / 300 * 100)
    assert contributions["A"] + contributions["B"] == pytest.approx(100.0)


def test_asset_contribution_to_drawdown_no_drawdown_is_zero():

    result = _result(
        equity_curve_by_symbol={"A": [1000, 1100, 1200], "B": [1000, 1050, 1100]},
        allocation={"A": 1000.0, "B": 1000.0},
    )

    contributions = asset_contribution_to_drawdown(result)

    assert contributions == {"A": 0.0, "B": 0.0}


# --- exposure_over_time -----------------------------------------------------------------


def test_exposure_over_time_correct():

    result = _result(
        equity_curve_by_symbol={"A": [600, 800], "B": [400, 200]},
        allocation={"A": 500.0, "B": 500.0},
    )

    exposure = exposure_over_time(result)

    assert exposure["A"] == pytest.approx([0.6, 0.8])
    assert exposure["B"] == pytest.approx([0.4, 0.2])


# --- concentration_risk_over_time --------------------------------------------------------


def test_concentration_risk_over_time_correct():

    result = _result(
        equity_curve_by_symbol={"A": [500, 900], "B": [500, 100]},
        allocation={"A": 500.0, "B": 500.0},
    )

    concentration = concentration_risk_over_time(result)

    assert concentration[0] == pytest.approx(0.5)  # 0.5^2 + 0.5^2
    assert concentration[1] == pytest.approx(0.82)  # 0.9^2 + 0.1^2


def test_concentration_risk_perfectly_diversified_across_n_assets():

    result = _result(
        equity_curve_by_symbol={"A": [250], "B": [250], "C": [250], "D": [250]},
        allocation={"A": 250.0, "B": 250.0, "C": 250.0, "D": 250.0},
    )

    concentration = concentration_risk_over_time(result)

    assert concentration[0] == pytest.approx(0.25)  # 1/4


# --- risk_per_asset ----------------------------------------------------------------------


def test_risk_per_asset_reuses_metrics_functions():

    result = _result(
        equity_curve_by_symbol={
            "A": [1000, 1100, 990, 1200],
            "B": [1000, 1000, 1000, 1000],
        },
        allocation={"A": 1000.0, "B": 1000.0},
    )

    risk = risk_per_asset(result, periods_per_year=4)

    expected_a = {
        "volatility_percent": volatility_percent(result.equity_curve_by_symbol["A"], 4),
        "sharpe_ratio": sharpe_ratio(result.equity_curve_by_symbol["A"], 4),
        "max_drawdown_percent": max_drawdown_percent(result.equity_curve_by_symbol["A"]),
    }

    assert risk["A"] == pytest.approx(expected_a)
