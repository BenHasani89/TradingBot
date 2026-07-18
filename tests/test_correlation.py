from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.backtest.correlation import market_correlation, strategy_correlation
from tradingbot.backtest.models import EquityPoint
from tradingbot.data.models import MarketCandle
from tradingbot.data.simulated_provider import SimulatedDataProvider


def _candles_from_closes(closes: list[float], symbol: str) -> list[MarketCandle]:

    now = datetime.now(UTC)
    return [
        MarketCandle(
            symbol=symbol,
            timestamp=now + timedelta(hours=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000,
        )
        for i, close in enumerate(closes)
    ]


def _curve(values: list[float]) -> list[EquityPoint]:

    now = datetime.now(UTC)
    return [EquityPoint(timestamp=now, total_value=v) for v in values]


# --- market_correlation ---------------------------------------------------------------


def test_market_correlation_perfectly_correlated_assets():

    a = _candles_from_closes([100, 110, 99, 108.9], "A")
    b = _candles_from_closes([50, 55, 49.5, 54.45], "B")  # identische prozentuale Bewegung

    result = market_correlation({"A": a, "B": b})

    assert result[("A", "B")] == pytest.approx(1.0, abs=1e-6)


def test_market_correlation_perfectly_anti_correlated_assets():

    a = _candles_from_closes([100, 110, 99, 108.9], "A")
    b = _candles_from_closes([100, 90, 99, 89.1], "B")  # exakt gegenlaeufige Bewegung

    result = market_correlation({"A": a, "B": b})

    assert result[("A", "B")] == pytest.approx(-1.0, abs=1e-6)


def test_market_correlation_returns_all_pairs_for_three_assets():

    provider = SimulatedDataProvider(seed=3)
    candles_by_symbol = {
        symbol: provider.get_candles(symbol=symbol, timeframe="1h", limit=15)
        for symbol in ["A", "B", "C"]
    }

    result = market_correlation(candles_by_symbol)

    assert set(result.keys()) == {("A", "B"), ("A", "C"), ("B", "C")}
    for value in result.values():
        assert -1.0 <= value <= 1.0


def test_market_correlation_too_few_points_is_omitted():

    a = _candles_from_closes([100], "A")
    b = _candles_from_closes([100, 110], "B")

    assert market_correlation({"A": a, "B": b}) == {}


# --- strategy_correlation ---------------------------------------------------------------


def test_strategy_correlation_perfectly_correlated():

    curve_a = _curve([1000, 1010, 990, 1005])
    curve_b = _curve([500, 505, 495, 502.5])  # exakt die Haelfte von A

    result = strategy_correlation({"A": curve_a, "B": curve_b})

    assert result[("A", "B")] == pytest.approx(1.0, abs=1e-6)


def test_strategy_correlation_handles_zero_value_periods():

    # Assets ohne offene Position zu manchen Zeitpunkten (Wert 0.0) duerfen
    # nicht zu einem Fehler fuehren (keine Renditenberechnung noetig, da
    # Wertniveaus statt Renditen korreliert werden).
    curve_a = _curve([1000, 0.0, 1000, 0.0, 1000])
    curve_b = _curve([500, 0.0, 500, 0.0, 500])

    result = strategy_correlation({"A": curve_a, "B": curve_b})

    assert ("A", "B") in result
    assert result[("A", "B")] == pytest.approx(1.0, abs=1e-6)


def test_strategy_correlation_skips_constant_series():

    curve_a = _curve([1000.0, 1000.0, 1000.0, 1000.0])
    curve_b = _curve([500, 505, 495, 502.5])

    assert strategy_correlation({"A": curve_a, "B": curve_b}) == {}
