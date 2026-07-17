import pytest

from tradingbot.data.simulated_provider import SimulatedDataProvider


def test_simulated_provider_returns_requested_amount():

    provider = SimulatedDataProvider()

    candles = provider.get_candles(symbol="BTCUSDT", timeframe="1h", limit=10)

    assert len(candles) == 10
    assert all(c.symbol == "BTCUSDT" for c in candles)


def test_simulated_provider_is_deterministic():

    provider = SimulatedDataProvider(seed=7)

    first = provider.get_candles(symbol="BTCUSDT", timeframe="1h", limit=5)
    second = provider.get_candles(symbol="BTCUSDT", timeframe="1h", limit=5)

    assert [c.close for c in first] == [c.close for c in second]


def test_simulated_provider_different_symbols_differ():

    provider = SimulatedDataProvider(seed=7)

    btc = provider.get_candles(symbol="BTCUSDT", timeframe="1h", limit=5)
    eth = provider.get_candles(symbol="ETHUSDT", timeframe="1h", limit=5)

    assert [c.close for c in btc] != [c.close for c in eth]


def test_simulated_provider_rejects_unknown_timeframe():

    provider = SimulatedDataProvider()

    with pytest.raises(ValueError):
        provider.get_candles(symbol="BTCUSDT", timeframe="banane", limit=5)
