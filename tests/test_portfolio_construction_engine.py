from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.backtest.portfolio_construction_engine import PortfolioConstructionEngine
from tradingbot.data.models import MarketCandle
from tradingbot.portfolio_construction.constraints import PortfolioConstraints
from tradingbot.portfolio_construction.rebalancing import PeriodicTrigger, RebalancingEngine
from tradingbot.portfolio_construction.target_allocation import EqualWeightPolicy


def _flat_candles(price: float, count: int, symbol: str) -> list[MarketCandle]:

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


def _build_engine(trigger, candle_count: int = 6, initial_capital: float = 1000.0):

    candles_by_symbol = {
        "A": _flat_candles(100.0, candle_count, "A"),
        "B": _flat_candles(100.0, candle_count, "B"),
    }
    rebalancing_engine = RebalancingEngine(
        policy=EqualWeightPolicy(),
        constraints=PortfolioConstraints(),
        trigger=trigger,
    )
    return PortfolioConstructionEngine(
        candles_by_symbol=candles_by_symbol,
        rebalancing_engine=rebalancing_engine,
        initial_capital=initial_capital,
    ), candles_by_symbol


def test_engine_records_allocation_history_every_step():

    engine, candles_by_symbol = _build_engine(PeriodicTrigger(every_n_steps=1))

    result = engine.run()

    assert len(result.allocation_history) == 5
    for weights in result.allocation_history:
        assert weights == pytest.approx({"A": 0.5, "B": 0.5})


def test_engine_executes_rebalancing_trades_and_updates_positions():

    engine, _ = _build_engine(PeriodicTrigger(every_n_steps=1))

    result = engine.run()

    assert result.trades >= 1
    assert len(result.rebalancing_events) >= 1
    assert result.equity_curve_by_symbol["A"][-1].total_value > 0
    assert result.equity_curve_by_symbol["B"][-1].total_value > 0


def test_engine_no_rebalancing_when_trigger_never_fires():

    engine, _ = _build_engine(PeriodicTrigger(every_n_steps=0))

    result = engine.run()

    assert result.rebalancing_events == []
    assert result.trades == 0
    # Kapital bleibt vollstaendig Cash -> Equity-Kurve bleibt konstant.
    assert all(point.total_value == pytest.approx(1000.0) for point in result.equity_curve)
    assert all(point.total_value == 0.0 for point in result.equity_curve_by_symbol["A"])


def test_engine_equity_curve_matches_synchronized_timestamps():

    engine, candles_by_symbol = _build_engine(PeriodicTrigger(every_n_steps=1), candle_count=6)

    result = engine.run()

    assert len(result.equity_curve) == 5
    expected_timestamps = [c.timestamp for c in candles_by_symbol["A"][1:]]
    assert [p.timestamp for p in result.equity_curve] == expected_timestamps


def test_engine_no_assets_returns_empty_result():

    rebalancing_engine = RebalancingEngine(
        policy=EqualWeightPolicy(),
        constraints=PortfolioConstraints(),
        trigger=PeriodicTrigger(every_n_steps=1),
    )
    engine = PortfolioConstructionEngine(
        candles_by_symbol={},
        rebalancing_engine=rebalancing_engine,
        initial_capital=1000.0,
    )

    result = engine.run()

    assert result.equity_curve == []
    assert result.equity_curve_by_symbol == {}
    assert result.allocation_history == []
    assert result.rebalancing_events == []
    assert result.trades == 0
    assert result.profit_loss == 0.0


def test_engine_capital_conserved_across_rebalancing():

    engine, _ = _build_engine(PeriodicTrigger(every_n_steps=1), candle_count=10)

    result = engine.run()

    # Konstante Kurse (_flat_candles) -> Rebalancing ohne Kursbewegung darf
    # das Gesamtkapital nicht veraendern (keine Gebuehren in dieser Engine).
    for point in result.equity_curve:
        assert point.total_value == pytest.approx(1000.0)
