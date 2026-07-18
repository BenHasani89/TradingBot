import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.backtest.models import BacktestResult, EquityPoint
from tradingbot.backtest.research_report import from_backtest_result
from tradingbot.data.models import MarketCandle
from tradingbot.research_tracking.models import (
    DatasetDescriptor,
    Experiment,
    ExperimentConfiguration,
    ExperimentMetadata,
    describe_dataset,
)


def _candles(symbol: str, count: int, start: datetime) -> list[MarketCandle]:

    return [
        MarketCandle(
            symbol=symbol,
            timestamp=start + timedelta(hours=i),
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=1000,
        )
        for i in range(count)
    ]


# --- describe_dataset --------------------------------------------------------------------


def test_describe_dataset_extracts_symbols_and_counts():

    start = datetime(2024, 1, 1, tzinfo=UTC)
    candles_by_symbol = {
        "BTCUSDT": _candles("BTCUSDT", 10, start),
        "ETHUSDT": _candles("ETHUSDT", 8, start),
    }

    descriptor = describe_dataset(
        candles_by_symbol, timeframe="1h", source="SimulatedDataProvider(seed=1)"
    )

    assert set(descriptor.symbols) == {"BTCUSDT", "ETHUSDT"}
    assert descriptor.candle_count == {"BTCUSDT": 10, "ETHUSDT": 8}
    assert descriptor.timeframe == "1h"
    assert descriptor.source == "SimulatedDataProvider(seed=1)"


def test_describe_dataset_computes_start_and_end_timestamp():

    start = datetime(2024, 1, 1, tzinfo=UTC)
    candles_by_symbol = {"BTCUSDT": _candles("BTCUSDT", 5, start)}

    descriptor = describe_dataset(candles_by_symbol, timeframe="1h", source="x")

    assert descriptor.start_timestamp == start
    assert descriptor.end_timestamp == start + timedelta(hours=4)


def test_describe_dataset_empty_input_returns_none_timestamps():

    descriptor = describe_dataset({}, timeframe="1h", source="x")

    assert descriptor.symbols == ()
    assert descriptor.candle_count == {}
    assert descriptor.start_timestamp is None
    assert descriptor.end_timestamp is None


def test_dataset_descriptor_is_frozen():

    descriptor = DatasetDescriptor(
        symbols=("A",),
        timeframe="1h",
        candle_count={"A": 1},
        start_timestamp=None,
        end_timestamp=None,
        source="x",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        descriptor.timeframe = "1d"


# --- Experiment referenziert ResearchReport ohne Kopie ------------------------------------


def test_experiment_references_report_without_copying():

    now = datetime.now(UTC)
    result = BacktestResult(
        trades=1,
        profit_loss=10.0,
        performance_percent=1.0,
        max_drawdown_percent=0.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=1010.0)],
        cycle_results=[],
    )
    report = from_backtest_result("Test", result, periods_per_year=252)

    metadata = ExperimentMetadata(
        experiment_id="abc",
        name=None,
        created_at=now,
        dataset=describe_dataset({}, timeframe="1h", source="x"),
        configuration=ExperimentConfiguration(
            component_type="Strategy", component_name="X", parameters={}, runner_type="Y"
        ),
        code_version=None,
    )
    experiment = Experiment(metadata=metadata, report=report)

    assert experiment.report is report
