from datetime import UTC, datetime

import pytest

from tradingbot.data.models import MarketCandle
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.simple import SimpleStrategy


def test_simple_strategy_buy():

    strategy = SimpleStrategy()

    candles = [
        MarketCandle(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            open=100,
            high=110,
            low=90,
            close=100,
            volume=1000,
        ),
        MarketCandle(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            open=100,
            high=120,
            low=95,
            close=110,
            volume=1200,
        ),
    ]

    signal = strategy.analyze(candles)

    assert signal.signal == "BUY"
    assert signal.symbol == "BTCUSDT"


def test_trading_signal_rejects_invalid_confidence():

    with pytest.raises(ValueError):
        TradingSignal(symbol="BTCUSDT", signal="BUY", confidence=1.5)

    with pytest.raises(ValueError):
        TradingSignal(symbol="BTCUSDT", signal="BUY", confidence=-0.1)


def test_strategy_name_defaults_to_class_name():

    strategy = SimpleStrategy()

    assert strategy.name == "SimpleStrategy"
