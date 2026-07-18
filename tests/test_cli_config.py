from tradingbot.cli.config import RuntimeConfig, build_config
from tradingbot.config.settings import DEFAULT_CAPITAL, MAX_RISK_PER_TRADE


def test_build_config_applies_sensible_defaults():

    config = build_config()

    assert isinstance(config, RuntimeConfig)
    assert config.symbol == "BTCUSDT"
    assert config.timeframe == "1h"
    assert config.initial_capital == DEFAULT_CAPITAL
    assert config.max_position_size == DEFAULT_CAPITAL * MAX_RISK_PER_TRADE
    assert config.session_id is None


def test_build_config_respects_explicit_overrides(tmp_path):

    custom_db_path = str(tmp_path / "custom.sqlite3")

    config = build_config(
        symbol="ETHUSDT",
        timeframe="4h",
        initial_capital=5000.0,
        max_position_size=100.0,
        db_path=custom_db_path,
        session_id="session-1",
    )

    assert config.symbol == "ETHUSDT"
    assert config.timeframe == "4h"
    assert config.initial_capital == 5000.0
    assert config.max_position_size == 100.0
    assert config.db_path == custom_db_path
    assert config.session_id == "session-1"


def test_build_config_default_db_path_is_stable_across_calls():

    first = build_config()
    second = build_config()

    assert first.db_path == second.db_path
