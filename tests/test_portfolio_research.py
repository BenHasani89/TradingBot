from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.backtest.portfolio_construction_optimization import (
    rank_portfolio_configurations,
)
from tradingbot.backtest.portfolio_research import PortfolioResearchRunner
from tradingbot.data.models import MarketCandle
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.portfolio_construction.constraints import PortfolioConstraints
from tradingbot.portfolio_construction.rebalancing import PeriodicTrigger, RebalancingEngine
from tradingbot.portfolio_construction.risk_policies import RiskParityPolicy
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


def _candles_by_symbol():

    return {"A": _flat_candles(100.0, 6, "A"), "B": _flat_candles(100.0, 6, "B")}


def test_portfolio_research_runner_returns_result_per_configuration():

    runner = PortfolioResearchRunner(candles_by_symbol=_candles_by_symbol(), initial_capital=1000.0)
    configs = {
        "EqualWeight-Periodic": RebalancingEngine(
            EqualWeightPolicy(), PortfolioConstraints(), PeriodicTrigger(1)
        ),
        "NeverRebalance": RebalancingEngine(
            EqualWeightPolicy(), PortfolioConstraints(), PeriodicTrigger(0)
        ),
    }

    results = runner.run_raw(configs)

    assert set(results.keys()) == {"EqualWeight-Periodic", "NeverRebalance"}
    assert results["EqualWeight-Periodic"].trades >= 1
    assert results["NeverRebalance"].trades == 0


def test_portfolio_research_runner_reusable_stateless_engine_across_configs():

    # Beweist, dass eine RebalancingEngine-Instanz unbedenklich fuer mehrere
    # benannte Konfigurationen wiederverwendet werden kann (zustandslos).
    runner = PortfolioResearchRunner(
        candles_by_symbol=_candles_by_symbol(), initial_capital=1000.0
    )
    shared_engine = RebalancingEngine(
        EqualWeightPolicy(), PortfolioConstraints(), PeriodicTrigger(1)
    )

    results = runner.run_raw({"Run1": shared_engine, "Run2": shared_engine, "Run3": shared_engine})

    profit_losses = [r.profit_loss for r in results.values()]
    assert all(value == pytest.approx(profit_losses[0]) for value in profit_losses)


def test_portfolio_research_runner_run_returns_comparison_rows():

    runner = PortfolioResearchRunner(
        candles_by_symbol=_candles_by_symbol(), initial_capital=1000.0
    )
    configs = {
        "Rebalance": RebalancingEngine(
            EqualWeightPolicy(), PortfolioConstraints(), PeriodicTrigger(1)
        )
    }

    rows = runner.run(configs)

    assert len(rows) == 1
    assert rows[0].configuration_name == "Rebalance"
    assert isinstance(rows[0].rebalancing_orders, int)
    assert rows[0].rebalancing_orders >= 1


def test_portfolio_research_end_to_end_with_ranking():

    candles_by_symbol = {
        "BTCUSDT": SimulatedDataProvider(seed=1).get_candles(
            symbol="BTCUSDT", timeframe="1h", limit=20
        ),
        "ETHUSDT": SimulatedDataProvider(seed=2).get_candles(
            symbol="ETHUSDT", timeframe="1h", limit=20
        ),
    }
    runner = PortfolioResearchRunner(candles_by_symbol=candles_by_symbol, initial_capital=10000.0)
    periods_per_year = {"BTCUSDT": 24 * 365, "ETHUSDT": 24 * 365}
    configs = {
        "EqualWeight": RebalancingEngine(
            EqualWeightPolicy(), PortfolioConstraints(), PeriodicTrigger(5)
        ),
        "RiskParity": RebalancingEngine(
            RiskParityPolicy(lookback=10, periods_per_year=periods_per_year),
            PortfolioConstraints(),
            PeriodicTrigger(5),
        ),
    }

    raw_results = runner.run_raw(configs)
    ranked = rank_portfolio_configurations(raw_results, periods_per_year=24 * 365)

    assert len(raw_results) == 2
    assert len(ranked) == 2
    assert {row.configuration_name for row in ranked} == {"EqualWeight", "RiskParity"}
