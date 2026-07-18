import json
from datetime import UTC, datetime

import pytest

from tradingbot.backtest.models import BacktestResult, EquityPoint
from tradingbot.backtest.research_report import ResearchSourceType, from_backtest_result
from tradingbot.research_tracking.models import DatasetDescriptor, ExperimentConfiguration
from tradingbot.research_tracking.storage import ExperimentLog, record_experiment, to_record


def _sample_report(name: str = "Test"):

    now = datetime.now(UTC)
    result = BacktestResult(
        trades=2,
        profit_loss=100.0,
        performance_percent=10.0,
        max_drawdown_percent=2.0,
        equity_curve=[EquityPoint(timestamp=now, total_value=v) for v in [1000.0, 1050.0, 1100.0]],
        cycle_results=[],
    )
    return from_backtest_result(name, result, periods_per_year=252)


def _sample_dataset() -> DatasetDescriptor:

    return DatasetDescriptor(
        symbols=("BTCUSDT",),
        timeframe="1h",
        candle_count={"BTCUSDT": 20},
        start_timestamp=None,
        end_timestamp=None,
        source="Test",
    )


def _sample_configuration() -> ExperimentConfiguration:

    return ExperimentConfiguration(
        component_type="Strategy",
        component_name="MovingAverageCrossoverStrategy",
        parameters={"short_window": 5, "long_window": 20},
        runner_type="BacktestResearchRunner",
    )


# --- record_experiment ---------------------------------------------------------------------


def test_record_experiment_generates_uuid_and_stores_in_log():

    log = ExperimentLog()

    experiment = record_experiment(
        log, _sample_report(), _sample_dataset(), _sample_configuration()
    )

    assert experiment.metadata.experiment_id
    assert len(experiment.metadata.experiment_id) == 36  # UUID4-Format
    assert experiment.metadata.name is None
    assert log.all() == [experiment]


def test_record_experiment_accepts_optional_name():

    log = ExperimentLog()

    experiment = record_experiment(
        log, _sample_report(), _sample_dataset(), _sample_configuration(), name="Mein Lauf"
    )

    assert experiment.metadata.name == "Mein Lauf"


def test_record_experiment_references_report_without_copy():

    log = ExperimentLog()
    report = _sample_report()

    experiment = record_experiment(log, report, _sample_dataset(), _sample_configuration())

    assert experiment.report is report


# --- ExperimentLog ------------------------------------------------------------------------


def test_experiment_log_all_returns_a_copy_not_the_internal_list():

    log = ExperimentLog()
    record_experiment(log, _sample_report(), _sample_dataset(), _sample_configuration())

    result = log.all()
    result.append("boese_manipulation")

    assert len(log.all()) == 1


def test_experiment_log_filter_by_source_type():

    log = ExperimentLog()
    record_experiment(log, _sample_report(), _sample_dataset(), _sample_configuration())

    strategy_results = log.filter_by_source_type(ResearchSourceType.STRATEGY_BACKTEST)
    portfolio_results = log.filter_by_source_type(ResearchSourceType.PORTFOLIO_BACKTEST)

    assert len(strategy_results) == 1
    assert portfolio_results == []


def test_experiment_log_latest_returns_most_recently_recorded():

    log = ExperimentLog()
    record_experiment(log, _sample_report("First"), _sample_dataset(), _sample_configuration())
    second = record_experiment(
        log, _sample_report("Second"), _sample_dataset(), _sample_configuration()
    )

    assert log.latest() is second


def test_experiment_log_latest_empty_log_returns_none():

    assert ExperimentLog().latest() is None


# --- to_record / export_json ---------------------------------------------------------------


def test_to_record_excludes_equity_curve_and_matches_report_metrics():

    experiment = record_experiment(
        ExperimentLog(), _sample_report(), _sample_dataset(), _sample_configuration()
    )

    record = to_record(experiment)

    assert not hasattr(record, "equity_curve")
    assert record.sharpe_ratio == experiment.report.sharpe_ratio
    assert record.performance_percent == experiment.report.performance_percent
    assert record.source_type == "strategy_backtest"


def test_export_json_produces_valid_json_without_equity_curve(tmp_path):

    log = ExperimentLog()
    experiment = record_experiment(
        log,
        _sample_report(),
        _sample_dataset(),
        _sample_configuration(),
        name="Export-Test",
    )

    output_path = tmp_path / "experiments.json"
    log.export_json(str(output_path))

    with open(output_path, encoding="utf-8") as file:
        data = json.load(file)

    assert len(data) == 1
    entry = data[0]
    assert entry["name"] == "Export-Test"
    assert entry["sharpe_ratio"] == pytest.approx(experiment.report.sharpe_ratio)
    assert "equity_curve" not in json.dumps(entry)


def test_export_json_handles_multiple_experiments(tmp_path):

    log = ExperimentLog()
    record_experiment(log, _sample_report("A"), _sample_dataset(), _sample_configuration())
    record_experiment(log, _sample_report("B"), _sample_dataset(), _sample_configuration())

    output_path = tmp_path / "experiments.json"
    log.export_json(str(output_path))

    with open(output_path, encoding="utf-8") as file:
        data = json.load(file)

    assert {entry["report_name"] for entry in data} == {"A", "B"}
