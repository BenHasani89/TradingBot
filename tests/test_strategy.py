from datetime import UTC, datetime

from tradingbot.data.models import MarketCandle
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
