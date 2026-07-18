from datetime import UTC, datetime

import pytest

from tradingbot.backtest.models import BacktestResult, EquityPoint
from tradingbot.backtest.multi_asset_metrics import (
    aggregate_multi_asset_results,
    rank_parameter_sets_by_robustness,
)
from tradingbot.backtest.optimization import rank_strategies


def _result_with_performance(performance_percent: float, initial_capital: float = 1000.0):
    """Baut ein konsistentes BacktestResult mit exakt gegebener
    Gesamtrendite (3 Punkte -> mit periods_per_year=3 entspricht 1 Jahr,
    annualisierte Rendite == performance_percent).
    """

    now = datetime.now(UTC)
    final_value = initial_capital * (1 + performance_percent / 100)
    mid_value = initial_capital * (1 + performance_percent / 200)
    equity_curve = [
        EquityPoint(timestamp=now, total_value=initial_capital),
        EquityPoint(timestamp=now, total_value=mid_value),
        EquityPoint(timestamp=now, total_value=final_value),
    ]

    return BacktestResult(
        trades=0,
        profit_loss=final_value - initial_capital,
        performance_percent=performance_percent,
        max_drawdown_percent=0.0,
        equity_curve=equity_curve,
        cycle_results=[],
    )


# --- aggregate_multi_asset_results ----------------------------------------------------


def test_aggregate_multi_asset_results_computes_correct_averages():

    periods_per_year = {"A": 3, "B": 3, "C": 3}
    results = {
        "A": _result_with_performance(10.0),
        "B": _result_with_performance(-4.0),
        "C": _result_with_performance(6.0),
    }

    summary = aggregate_multi_asset_results(results, periods_per_year)

    assert summary.asset_count == 3
    assert summary.average_performance_percent == pytest.approx(4.0)
    # 2 von 3 Assets mit positiver Performance.
    assert summary.profitable_asset_ratio_percent == pytest.approx(200 / 3)


def test_aggregate_multi_asset_results_respects_per_asset_periods_per_year():

    result_a = _result_with_performance(10.0)
    result_b = _result_with_performance(10.0)

    summary = aggregate_multi_asset_results({"A": result_a, "B": result_b}, {"A": 1, "B": 100})

    ranked_a = rank_strategies({"A": result_a}, periods_per_year=1)[0]
    ranked_b = rank_strategies({"B": result_b}, periods_per_year=100)[0]

    # Identischer Kursverlauf, aber unterschiedliches periods_per_year ->
    # unterschiedliche Sharpe Ratios; der Durchschnitt muss das widerspiegeln.
    assert ranked_a.sharpe_ratio != pytest.approx(ranked_b.sharpe_ratio)
    assert summary.average_sharpe_ratio == pytest.approx(
        (ranked_a.sharpe_ratio + ranked_b.sharpe_ratio) / 2
    )


def test_aggregate_multi_asset_results_empty_is_zero():

    summary = aggregate_multi_asset_results({}, {})

    assert summary.asset_count == 0
    assert summary.average_performance_percent == 0.0
    assert summary.average_sharpe_ratio == 0.0
    assert summary.performance_std_dev == 0.0
    assert summary.profitable_asset_ratio_percent == 0.0


# --- rank_parameter_sets_by_robustness -------------------------------------------------


def test_rank_parameter_sets_by_robustness_prefers_consistent_over_peak():

    periods_per_year = {"A": 3, "B": 3}
    results_by_variant = {
        "InkonsistentGut": {
            "A": _result_with_performance(50.0),
            "B": _result_with_performance(-30.0),
        },
        "KonsistentGut": {
            "A": _result_with_performance(12.0),
            "B": _result_with_performance(10.0),
        },
    }

    ranked = rank_parameter_sets_by_robustness(
        results_by_variant, periods_per_year, sort_by="average_performance_percent"
    )

    # InkonsistentGut: (50-30)/2=10%, KonsistentGut: (12+10)/2=11% -> Konsistent gewinnt,
    # obwohl kein Einzelwert an das Spitzenergebnis von 50% herankommt.
    assert ranked[0].strategy_name == "KonsistentGut"
    assert ranked[0].summary.average_performance_percent == pytest.approx(11.0)
    assert ranked[1].strategy_name == "InkonsistentGut"
    assert ranked[1].summary.average_performance_percent == pytest.approx(10.0)


def test_rank_parameter_sets_by_robustness_default_sort_by_sharpe():

    periods_per_year = {"A": 3}
    results_by_variant = {
        "Positiv": {"A": _result_with_performance(5.0)},
        "Negativ": {"A": _result_with_performance(-5.0)},
    }

    ranked = rank_parameter_sets_by_robustness(results_by_variant, periods_per_year)

    assert ranked[0].strategy_name == "Positiv"


def test_rank_parameter_sets_by_robustness_includes_per_asset_results():

    periods_per_year = {"A": 3, "B": 3}
    results_by_variant = {
        "V1": {"A": _result_with_performance(10.0), "B": _result_with_performance(20.0)},
    }

    ranked = rank_parameter_sets_by_robustness(results_by_variant, periods_per_year)

    assert set(ranked[0].results_by_asset.keys()) == {"A", "B"}
    assert ranked[0].results_by_asset["A"].performance_percent == pytest.approx(10.0)
    assert ranked[0].results_by_asset["B"].performance_percent == pytest.approx(20.0)


def test_rank_parameter_sets_by_robustness_invalid_sort_by_raises():

    periods_per_year = {"A": 3}
    results_by_variant = {"V1": {"A": _result_with_performance(10.0)}}

    with pytest.raises(AttributeError):
        rank_parameter_sets_by_robustness(
            results_by_variant, periods_per_year, sort_by="not_a_field"
        )
