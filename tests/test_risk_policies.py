from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.data.models import MarketCandle
from tradingbot.portfolio_construction.risk_policies import (
    RiskParityPolicy,
    VolatilityTargetPolicy,
)
from tradingbot.portfolio_construction.target_allocation import EqualWeightPolicy


def _candles_from_closes(closes: list[float], symbol: str) -> list[MarketCandle]:

    now = datetime.now(UTC)
    return [
        MarketCandle(
            symbol=symbol,
            timestamp=now + timedelta(hours=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000,
        )
        for i, close in enumerate(closes)
    ]


# --- RiskParityPolicy -------------------------------------------------------------------


def test_risk_parity_weights_inversely_proportional_to_volatility():

    volatile = _candles_from_closes([100, 120, 90, 130, 80], "A")
    stable = _candles_from_closes([100, 101, 99, 101, 99], "B")
    policy = RiskParityPolicy(lookback=5, periods_per_year={"A": 252, "B": 252})

    weights = policy.target_weights({"A": volatile, "B": stable})

    assert weights["B"] > weights["A"]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_risk_parity_falls_back_to_equal_weight_without_volatility_data():

    # Nur eine Kerze je Asset -> keine Rendite berechenbar.
    flat_a = _candles_from_closes([100], "A")
    flat_b = _candles_from_closes([100], "B")
    policy = RiskParityPolicy(lookback=5, periods_per_year={"A": 252, "B": 252})

    weights = policy.target_weights({"A": flat_a, "B": flat_b})

    assert weights == pytest.approx({"A": 0.5, "B": 0.5})


def test_risk_parity_empty_symbols():

    policy = RiskParityPolicy(lookback=5, periods_per_year={})

    assert policy.target_weights({}) == {}


def test_risk_parity_uses_only_lookback_window():

    # Erste 5 Kerzen von A sehr volatil, letzte 3 (= kurzer Lookback) stabil.
    volatile_then_stable = [100, 200, 50, 180, 60, 100, 101, 100]
    candles_a = _candles_from_closes(volatile_then_stable, "A")
    candles_b = _candles_from_closes([100, 101, 100, 101, 100, 100, 101, 100], "B")

    policy_full_history = RiskParityPolicy(lookback=8, periods_per_year={"A": 252, "B": 252})
    policy_short_lookback = RiskParityPolicy(lookback=3, periods_per_year={"A": 252, "B": 252})

    weights_full = policy_full_history.target_weights({"A": candles_a, "B": candles_b})
    weights_short = policy_short_lookback.target_weights({"A": candles_a, "B": candles_b})

    # Mit vollem Verlauf ist A deutlich volatiler -> bekommt viel weniger Gewicht.
    # Mit kurzem Lookback (nur die stabilen letzten 3 Kerzen von A) naehern sich
    # die Gewichte einander an.
    assert weights_full["A"] < weights_short["A"]


# --- VolatilityTargetPolicy --------------------------------------------------------------


def test_volatility_target_policy_no_scaling_when_under_target():

    base = EqualWeightPolicy()
    candles_by_symbol = {
        "A": _candles_from_closes([100, 101, 100, 101], "A"),
        "B": _candles_from_closes([100, 101, 100, 101], "B"),
    }
    policy = VolatilityTargetPolicy(
        base_policy=base,
        target_volatility_percent=1000.0,
        lookback=4,
        periods_per_year={"A": 252, "B": 252},
    )

    weights = policy.target_weights(candles_by_symbol)

    assert weights == base.target_weights(candles_by_symbol)


def test_volatility_target_policy_scales_down_when_over_target():

    base = EqualWeightPolicy()
    volatile_closes = [100, 150, 80, 160, 70]
    candles_by_symbol = {
        "A": _candles_from_closes(volatile_closes, "A"),
        "B": _candles_from_closes(volatile_closes, "B"),
    }
    policy = VolatilityTargetPolicy(
        base_policy=base,
        target_volatility_percent=1.0,
        lookback=5,
        periods_per_year={"A": 1, "B": 1},
    )

    weights = policy.target_weights(candles_by_symbol)
    base_weights = base.target_weights(candles_by_symbol)

    assert sum(weights.values()) < sum(base_weights.values())
    # Gleichmaessige Skalierung -> Verhaeltnis zwischen den Assets bleibt erhalten.
    assert weights["A"] == pytest.approx(weights["B"])


def test_volatility_target_policy_empty_base_weights():

    policy = VolatilityTargetPolicy(
        base_policy=EqualWeightPolicy(),
        target_volatility_percent=10.0,
        lookback=5,
        periods_per_year={},
    )

    assert policy.target_weights({}) == {}
