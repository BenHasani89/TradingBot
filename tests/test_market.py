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


# --- Dedup (Idempotenz) -----------------------------------------------------------------------


def _candle(symbol: str, timestamp: datetime, close: float = 100.0) -> MarketCandle:

    return MarketCandle(
        symbol=symbol,
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
    )


def test_add_returns_true_for_new_candle():

    store = MarketDataStore()

    assert store.add(_candle("BTCUSDT", datetime(2026, 7, 18, 12, tzinfo=UTC))) is True


def test_add_returns_false_for_already_known_candle():

    store = MarketDataStore()
    timestamp = datetime(2026, 7, 18, 12, tzinfo=UTC)
    store.add(_candle("BTCUSDT", timestamp))

    assert store.add(_candle("BTCUSDT", timestamp)) is False
    assert len(store.all()) == 1


def test_add_treats_same_timestamp_different_symbol_as_new():

    store = MarketDataStore()
    timestamp = datetime(2026, 7, 18, 12, tzinfo=UTC)
    store.add(_candle("BTCUSDT", timestamp))

    assert store.add(_candle("ETHUSDT", timestamp)) is True
    assert len(store.all()) == 2


def test_add_many_returns_only_genuinely_new_candles():

    store = MarketDataStore()
    t1 = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 7, 18, 12, 1, tzinfo=UTC)
    t3 = datetime(2026, 7, 18, 12, 2, tzinfo=UTC)
    store.add(_candle("BTCUSDT", t1))

    new_candles = store.add_many(
        [_candle("BTCUSDT", t1), _candle("BTCUSDT", t2), _candle("BTCUSDT", t3)]
    )

    assert [c.timestamp for c in new_candles] == [t2, t3]
    assert len(store.all()) == 3


def test_add_many_with_no_new_candles_returns_empty_list():

    store = MarketDataStore()
    timestamp = datetime(2026, 7, 18, 12, tzinfo=UTC)
    store.add(_candle("BTCUSDT", timestamp))

    assert store.add_many([_candle("BTCUSDT", timestamp)]) == []
