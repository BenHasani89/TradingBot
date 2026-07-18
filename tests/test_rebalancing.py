from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.data.models import MarketCandle
from tradingbot.portfolio.models import PortfolioStatus, Position
from tradingbot.portfolio_construction.constraints import PortfolioConstraints
from tradingbot.portfolio_construction.rebalancing import (
    DriftTrigger,
    PeriodicTrigger,
    RebalancingEngine,
)
from tradingbot.portfolio_construction.target_allocation import (
    EqualWeightPolicy,
    FixedTargetPolicy,
)


def _candles(symbol: str, count: int = 3, price: float = 100.0) -> list[MarketCandle]:

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


# --- PeriodicTrigger ---------------------------------------------------------------------


def test_periodic_trigger_fires_on_multiples():

    trigger = PeriodicTrigger(every_n_steps=5)

    assert trigger.should_rebalance(0, {}, {}) is True
    assert trigger.should_rebalance(5, {}, {}) is True
    assert trigger.should_rebalance(3, {}, {}) is False


def test_periodic_trigger_zero_never_fires():

    trigger = PeriodicTrigger(every_n_steps=0)

    assert trigger.should_rebalance(0, {}, {}) is False


# --- DriftTrigger ------------------------------------------------------------------------


def test_drift_trigger_fires_when_deviation_exceeds_threshold():

    trigger = DriftTrigger(max_drift_percent=5.0)

    assert trigger.should_rebalance(0, {"A": 0.5, "B": 0.5}, {"A": 0.6, "B": 0.4}) is True


def test_drift_trigger_does_not_fire_within_threshold():

    trigger = DriftTrigger(max_drift_percent=15.0)

    assert trigger.should_rebalance(0, {"A": 0.5, "B": 0.5}, {"A": 0.6, "B": 0.4}) is False


# --- RebalancingEngine.generate_rebalancing_orders ----------------------------------------


def test_generate_rebalancing_orders_no_orders_when_trigger_does_not_fire():

    engine = RebalancingEngine(
        policy=EqualWeightPolicy(),
        constraints=PortfolioConstraints(),
        trigger=PeriodicTrigger(every_n_steps=10),
    )
    status = PortfolioStatus(capital=1000.0, positions=[])

    orders = engine.generate_rebalancing_orders(
        candles_by_symbol={"A": _candles("A"), "B": _candles("B")},
        current_prices={"A": 100.0, "B": 100.0},
        portfolio_status=status,
        step_index=3,
    )

    assert orders == []


def test_generate_rebalancing_orders_buys_to_reach_target_from_all_cash():

    engine = RebalancingEngine(
        policy=EqualWeightPolicy(),
        constraints=PortfolioConstraints(),
        trigger=PeriodicTrigger(every_n_steps=1),
    )
    status = PortfolioStatus(capital=1000.0, positions=[])

    orders = engine.generate_rebalancing_orders(
        candles_by_symbol={"A": _candles("A"), "B": _candles("B")},
        current_prices={"A": 100.0, "B": 100.0},
        portfolio_status=status,
        step_index=0,
    )

    by_symbol = {order.symbol: order for order in orders}
    assert len(orders) == 2
    assert by_symbol["A"].side == "BUY"
    assert by_symbol["A"].quantity == pytest.approx(5.0)
    assert by_symbol["B"].side == "BUY"
    assert by_symbol["B"].quantity == pytest.approx(5.0)


def test_generate_rebalancing_orders_sells_overweight_position():

    engine = RebalancingEngine(
        policy=EqualWeightPolicy(),
        constraints=PortfolioConstraints(),
        trigger=PeriodicTrigger(every_n_steps=1),
    )
    # A ist stark uebergewichtet (800 von 1000 Gesamtwert), B fehlt komplett.
    status = PortfolioStatus(
        capital=200.0,
        positions=[Position(symbol="A", quantity=8.0, entry_price=100.0)],
    )

    orders = engine.generate_rebalancing_orders(
        candles_by_symbol={"A": _candles("A"), "B": _candles("B")},
        current_prices={"A": 100.0, "B": 100.0},
        portfolio_status=status,
        step_index=0,
    )

    by_symbol = {order.symbol: order for order in orders}
    assert by_symbol["A"].side == "SELL"
    assert by_symbol["A"].quantity == pytest.approx(3.0)  # 800 -> 500 Zielwert
    assert by_symbol["B"].side == "BUY"
    assert by_symbol["B"].quantity == pytest.approx(5.0)  # 0 -> 500 Zielwert


def test_generate_rebalancing_orders_respects_constraints():

    engine = RebalancingEngine(
        policy=FixedTargetPolicy({"A": 0.9, "B": 0.1}),
        constraints=PortfolioConstraints(max_weight_per_asset=0.5),
        trigger=PeriodicTrigger(every_n_steps=1),
    )
    status = PortfolioStatus(capital=1000.0, positions=[])

    orders = engine.generate_rebalancing_orders(
        candles_by_symbol={"A": _candles("A"), "B": _candles("B")},
        current_prices={"A": 100.0, "B": 100.0},
        portfolio_status=status,
        step_index=0,
    )

    by_symbol = {order.symbol: order for order in orders}
    # A wird durch die Constraint auf 0.5 gekappt statt 0.9.
    assert by_symbol["A"].quantity == pytest.approx(5.0)


def test_generate_rebalancing_orders_no_orders_when_already_at_target():

    engine = RebalancingEngine(
        policy=EqualWeightPolicy(),
        constraints=PortfolioConstraints(),
        trigger=PeriodicTrigger(every_n_steps=1),
    )
    status = PortfolioStatus(
        capital=0.0,
        positions=[
            Position(symbol="A", quantity=5.0, entry_price=100.0),
            Position(symbol="B", quantity=5.0, entry_price=100.0),
        ],
    )

    orders = engine.generate_rebalancing_orders(
        candles_by_symbol={"A": _candles("A"), "B": _candles("B")},
        current_prices={"A": 100.0, "B": 100.0},
        portfolio_status=status,
        step_index=0,
    )

    assert orders == []
