from datetime import UTC, datetime

from tradingbot.data.market import MarketDataStore
from tradingbot.data.models import MarketCandle


def test_market_data_store():

    store = MarketDataStore()

    candle = MarketCandle(
        symbol="BTCUSDT",
        timestamp=datetime.now(UTC),
        open=100,
        high=110,
        low=90,
        close=105,
        volume=1000,
    )

    store.add(candle)

    assert len(store.all()) == 1
    assert store.all()[0].symbol == "BTCUSDT"
