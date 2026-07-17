from datetime import UTC, datetime

from tradingbot.backtest.parameter_grid import build_strategy_variants, generate_parameter_grid
from tradingbot.data.models import MarketCandle
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.buy_and_hold import BuyAndHoldStrategy
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy


class _RecordingParamsStrategy(Strategy):
    """Test-Doppel ohne jeden Bezug zu einer echten Strategie - speichert nur
    die erhaltenen Konstruktor-Parameter, um Generizität zu beweisen.
    """

    def __init__(self, **kwargs):
        self.params = kwargs

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        return TradingSignal(symbol="TEST", signal="HOLD", confidence=0.0)


def _candles(closes: list[float], symbol: str = "BTCUSDT"):

    now = datetime.now(UTC)
    return [
        MarketCandle(
            symbol=symbol,
            timestamp=now,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000,
        )
        for close in closes
    ]


# --- generate_parameter_grid --------------------------------------------------------


def test_generate_parameter_grid_produces_cartesian_product():

    grid = generate_parameter_grid({"short_window": [5, 10], "long_window": [20, 50]})

    assert len(grid) == 4
    assert {"short_window": 5, "long_window": 20} in grid
    assert {"short_window": 5, "long_window": 50} in grid
    assert {"short_window": 10, "long_window": 20} in grid
    assert {"short_window": 10, "long_window": 50} in grid


def test_generate_parameter_grid_single_parameter():

    grid = generate_parameter_grid({"short_window": [5, 10, 20]})

    assert len(grid) == 3
    assert {"short_window": 5} in grid
    assert {"short_window": 10} in grid
    assert {"short_window": 20} in grid


def test_generate_parameter_grid_three_parameters():

    grid = generate_parameter_grid({"a": [1, 2], "b": [10], "c": [100, 200]})

    assert len(grid) == 4  # 2 * 1 * 2


def test_generate_parameter_grid_empty_grid_returns_single_empty_dict():

    assert generate_parameter_grid({}) == [{}]


# --- build_strategy_variants: generisch, ohne Strategie-Wissen ---------------------


def test_build_strategy_variants_applies_correct_parameters():

    variants = build_strategy_variants(_RecordingParamsStrategy, {"a": [1, 2], "b": [10]})

    assert len(variants) == 2
    seen_a_values = sorted(strategy.params["a"] for strategy in variants.values())
    assert seen_a_values == [1, 2]
    assert all(strategy.params["b"] == 10 for strategy in variants.values())


def test_build_strategy_variants_labels_are_unique_and_readable():

    variants = build_strategy_variants(_RecordingParamsStrategy, {"a": [1, 2]})

    assert len(variants) == 2
    for label in variants:
        assert "_RecordingParamsStrategy" in label
        assert "a=" in label


def test_build_strategy_variants_empty_grid_returns_single_default_instance():

    variants = build_strategy_variants(_RecordingParamsStrategy, {})

    assert len(variants) == 1


# --- Zusaetzlich mit einer echten Produktions-Strategie -----------------------------


def test_build_strategy_variants_works_with_moving_average_strategy():

    variants = build_strategy_variants(
        MovingAverageCrossoverStrategy,
        {"short_window": [2], "long_window": [3]},
    )

    assert len(variants) == 1
    strategy = next(iter(variants.values()))
    assert isinstance(strategy, MovingAverageCrossoverStrategy)

    # long_window=3 -> mit nur 2 Kerzen noch HOLD (zu wenig Daten), beweist,
    # dass der Parameter tatsaechlich angewendet wurde.
    assert strategy.analyze(_candles([100.0, 110.0])).signal == "HOLD"
    assert strategy.analyze(_candles([100.0, 110.0, 120.0])).signal in ("BUY", "SELL")


def test_build_strategy_variants_is_generic_for_different_strategy_class():

    variants = build_strategy_variants(BuyAndHoldStrategy, {"symbol": ["BTC", "ETH"]})

    assert len(variants) == 2
    assert all(isinstance(strategy, BuyAndHoldStrategy) for strategy in variants.values())
