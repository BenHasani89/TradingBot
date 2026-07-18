from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.data.models import MarketCandle
from tradingbot.portfolio.models import PortfolioStatus, Position
from tradingbot.portfolio_construction.target_allocation import (
    EqualWeightPolicy,
    FixedTargetPolicy,
)


def _candles(symbol: str, count: int = 5, price: float = 100.0) -> list[MarketCandle]:

    now = datetime.now(UTC)
    return [
        MarketCandle(
            symbol=symbol,
            timestamp=now + timedelta(hours=i),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000,
        )
        for i in range(count)
    ]


# --- EqualWeightPolicy -----------------------------------------------------------------


def test_equal_weight_policy_splits_evenly():

    policy = EqualWeightPolicy()
    candles_by_symbol = {"A": _candles("A"), "B": _candles("B"), "C": _candles("C")}

    weights = policy.target_weights(candles_by_symbol)

    assert weights == pytest.approx({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})


def test_equal_weight_policy_empty_symbols():

    assert EqualWeightPolicy().target_weights({}) == {}


def test_equal_weight_policy_ignores_portfolio_status():

    policy = EqualWeightPolicy()
    candles_by_symbol = {"A": _candles("A"), "B": _candles("B")}
    status = PortfolioStatus(
        capital=500.0,
        positions=[Position(symbol="A", quantity=10.0, entry_price=50.0)],
    )

    weights = policy.target_weights(candles_by_symbol, portfolio_status=status)

    assert weights == pytest.approx({"A": 0.5, "B": 0.5})


# --- FixedTargetPolicy ------------------------------------------------------------------


def test_fixed_target_policy_returns_configured_weights():

    policy = FixedTargetPolicy({"BTC": 0.6, "ETH": 0.4})

    weights = policy.target_weights({"BTC": _candles("BTC"), "ETH": _candles("ETH")})

    assert weights == {"BTC": 0.6, "ETH": 0.4}


def test_fixed_target_policy_ignores_candles_and_portfolio_status():

    policy = FixedTargetPolicy({"BTC": 1.0})

    assert policy.target_weights({}) == {"BTC": 1.0}
