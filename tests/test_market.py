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


def test_market_data_store_latest_filters_by_symbol_and_limit():

    store = MarketDataStore()

    for i in range(3):
        store.add(
            MarketCandle(
                symbol="BTCUSDT",
                timestamp=datetime.now(UTC),
                open=100 + i,
                high=110 + i,
                low=90 + i,
                close=105 + i,
                volume=1000,
            )
        )

    store.add(
        MarketCandle(
            symbol="ETHUSDT",
            timestamp=datetime.now(UTC),
            open=200,
            high=210,
            low=190,
            close=205,
            volume=500,
        )
    )

    latest = store.latest("BTCUSDT", limit=2)

    assert len(latest) == 2
    assert all(c.symbol == "BTCUSDT" for c in latest)
    assert latest[-1].close == 107
