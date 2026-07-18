from datetime import UTC, datetime, timedelta

from tradingbot.backtest.walk_forward import (
    WalkForwardRunner,
    generate_walk_forward_windows,
)
from tradingbot.data.models import MarketCandle
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.buy_and_hold import BuyAndHoldStrategy
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy


def _candles(n: int, symbol: str = "BTCUSDT"):
    """Kerzen mit eindeutigem, aufsteigendem Schlusskurs (= Index) - macht
    exakte Fenstergrenzen einfach prüfbar.
    """

    now = datetime.now(UTC)
    return [
        MarketCandle(
            symbol=symbol,
            timestamp=now + timedelta(hours=i),
            open=float(i),
            high=float(i),
            low=float(i),
            close=float(i),
            volume=1000,
        )
        for i in range(n)
    ]


# --- generate_walk_forward_windows ---------------------------------------------------


def test_generate_walk_forward_windows_expanding_train_size():

    windows = generate_walk_forward_windows(
        _candles(350), initial_train_size=200, out_of_sample_size=50
    )

    assert len(windows) == 3
    assert len(windows[0].in_sample) == 200
    assert len(windows[1].in_sample) == 250
    assert len(windows[2].in_sample) == 300
    assert all(len(w.out_of_sample) == 50 for w in windows)


def test_generate_walk_forward_windows_correct_oos_boundaries():

    windows = generate_walk_forward_windows(
        _candles(350), initial_train_size=200, out_of_sample_size=50
    )

    assert windows[0].in_sample[-1].close == 199.0
    assert windows[0].out_of_sample[0].close == 200.0
    assert windows[0].out_of_sample[-1].close == 249.0

    assert windows[1].in_sample[-1].close == 249.0
    assert windows[1].out_of_sample[0].close == 250.0
    assert windows[1].out_of_sample[-1].close == 299.0

    assert windows[2].in_sample[-1].close == 299.0
    assert windows[2].out_of_sample[0].close == 300.0
    assert windows[2].out_of_sample[-1].close == 349.0


def test_generate_walk_forward_windows_no_data_leak_between_in_sample_and_out_of_sample():

    windows = generate_walk_forward_windows(
        _candles(350), initial_train_size=200, out_of_sample_size=50
    )

    for window in windows:
        in_sample_closes = {c.close for c in window.in_sample}
        oos_closes = {c.close for c in window.out_of_sample}
        assert in_sample_closes.isdisjoint(oos_closes)


def test_generate_walk_forward_windows_window_indices_sequential():

    windows = generate_walk_forward_windows(
        _candles(350), initial_train_size=200, out_of_sample_size=50
    )

    assert [w.window_index for w in windows] == [0, 1, 2]


def test_generate_walk_forward_windows_insufficient_data_returns_empty_list():

    windows = generate_walk_forward_windows(
        _candles(100), initial_train_size=200, out_of_sample_size=50
    )

    assert windows == []


def test_generate_walk_forward_windows_zero_out_of_sample_size_returns_empty_list():

    windows = generate_walk_forward_windows(
        _candles(1000), initial_train_size=200, out_of_sample_size=0
    )

    assert windows == []


# --- WalkForwardRunner ----------------------------------------------------------------


def test_walk_forward_runner_produces_expected_window_count():

    candles = SimulatedDataProvider(seed=1).get_candles(symbol="BTCUSDT", timeframe="1h", limit=40)
    runner = WalkForwardRunner(
        candles=candles,
        strategy_class=MovingAverageCrossoverStrategy,
        param_grid={"short_window": [2, 3], "long_window": [5, 8]},
        initial_capital=10000.0,
        risk_limit=1000.0,
        periods_per_year=24 * 365,
        initial_train_size=20,
        out_of_sample_size=10,
    )

    results = runner.run()

    # 40 Kerzen, train=20, oos=10 -> Fenster bei train_end=20 (20+10<=40) und
    # train_end=30 (30+10<=40); train_end=40 waere zu gross (40+10>40).
    assert len(results) == 2
    assert [r.window_index for r in results] == [0, 1]


def test_walk_forward_runner_in_sample_ranking_contains_all_variants():

    candles = SimulatedDataProvider(seed=4).get_candles(symbol="BTCUSDT", timeframe="1h", limit=30)
    runner = WalkForwardRunner(
        candles=candles,
        strategy_class=MovingAverageCrossoverStrategy,
        param_grid={"short_window": [2, 3, 4], "long_window": [5, 8, 10]},
        initial_capital=10000.0,
        risk_limit=1000.0,
        periods_per_year=24 * 365,
        initial_train_size=20,
        out_of_sample_size=10,
    )

    results = runner.run()

    assert len(results) == 1
    # Alle 9 Parameter-Kombinationen (3x3) wurden im In-Sample-Schritt gerankt.
    assert len(results[0].in_sample_ranking) == 9


def test_walk_forward_runner_out_of_sample_uses_only_winner():

    candles = SimulatedDataProvider(seed=6).get_candles(symbol="BTCUSDT", timeframe="1h", limit=30)
    runner = WalkForwardRunner(
        candles=candles,
        strategy_class=MovingAverageCrossoverStrategy,
        param_grid={"short_window": [2, 3, 4], "long_window": [5, 8, 10]},
        initial_capital=10000.0,
        risk_limit=1000.0,
        periods_per_year=24 * 365,
        initial_train_size=20,
        out_of_sample_size=10,
    )

    results = runner.run()

    window_result = results[0]
    # Das einzige Out-of-Sample-Ergebnis gehoert zur Gewinnerstrategie.
    assert window_result.out_of_sample_result.strategy_name == window_result.winning_strategy_name
    in_sample_names = {row.strategy_name for row in window_result.in_sample_ranking}
    assert window_result.winning_strategy_name in in_sample_names


class _TrackingStrategy(Strategy):
    """Test-Doppel: jede Instanz zählt ihre eigenen `analyze()`-Aufrufe.

    Beweist auf Instanzebene, dass im Out-of-Sample-Schritt ausschliesslich
    die Gewinner-Instanz tatsächlich ausgeführt wird.
    """

    instances: list["_TrackingStrategy"] = []

    def __init__(self, marker: int) -> None:
        self.marker = marker
        self.call_count = 0
        _TrackingStrategy.instances.append(self)

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        self.call_count += 1
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        return TradingSignal(symbol=symbol, signal="HOLD", confidence=0.0)


def test_walk_forward_runner_out_of_sample_only_runs_winner_not_other_candidates():

    _TrackingStrategy.instances = []

    candles = SimulatedDataProvider(seed=7).get_candles(symbol="BTCUSDT", timeframe="1h", limit=30)
    runner = WalkForwardRunner(
        candles=candles,
        strategy_class=_TrackingStrategy,
        param_grid={"marker": [1, 2, 3]},
        initial_capital=10000.0,
        risk_limit=1000.0,
        periods_per_year=24 * 365,
        initial_train_size=20,
        out_of_sample_size=10,
    )

    results = runner.run()

    assert len(results) == 1
    # 3 Varianten x 2 Instanziierungsrunden (In-Sample + Out-of-Sample) = 6.
    assert len(_TrackingStrategy.instances) == 6

    # Die zweite Haelfte sind die frischen Out-of-Sample-Instanzen.
    oos_instances = _TrackingStrategy.instances[3:]
    called = [i for i in oos_instances if i.call_count > 0]
    not_called = [i for i in oos_instances if i.call_count == 0]

    assert len(called) == 1
    assert len(not_called) == 2


class _BuyThenSellOnceStrategy(Strategy):
    """Test-Doppel: kauft beim ersten `analyze()`-Aufruf, verkauft beim
    zweiten, danach nur noch HOLD.

    Bei geteiltem Zustand zwischen Fenstern würde eine wiederverwendete
    Instanz in einem späteren Fenster keinen (neuen) abgeschlossenen Trade
    mehr erzeugen, da BUY/SELL bereits "verbraucht" wären - eine frische
    Instanz je Fenster erzeugt dagegen in jedem Fenster genau einen
    abgeschlossenen Trade.
    """

    def __init__(self, symbol: str) -> None:
        self._symbol = symbol
        self._step = 0

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        self._step += 1
        if self._step == 1:
            return TradingSignal(symbol=self._symbol, signal="BUY", confidence=1.0)
        if self._step == 2:
            return TradingSignal(symbol=self._symbol, signal="SELL", confidence=1.0)
        return TradingSignal(symbol=self._symbol, signal="HOLD", confidence=0.0)


def test_walk_forward_runner_isolates_strategy_state_between_windows():

    candles = SimulatedDataProvider(seed=8).get_candles(symbol="BTCUSDT", timeframe="1h", limit=40)
    runner = WalkForwardRunner(
        candles=candles,
        strategy_class=_BuyThenSellOnceStrategy,
        param_grid={"symbol": ["BTCUSDT"]},
        initial_capital=10000.0,
        risk_limit=1000.0,
        periods_per_year=24 * 365,
        initial_train_size=20,
        out_of_sample_size=10,
    )

    results = runner.run()

    assert len(results) == 2
    # Jede frische Out-of-Sample-Instanz durchlaeuft BUY -> SELL -> HOLD*,
    # erzeugt also genau einen abgeschlossenen Trade. Waere Zustand zwischen
    # Fenstern geteilt, haette die Instanz BUY/SELL bereits "verbraucht" und
    # wuerde nur noch HOLD liefern (trades=0).
    for window_result in results:
        assert window_result.out_of_sample_result.trades == 1


def test_walk_forward_runner_insufficient_data_returns_empty_list():

    candles = SimulatedDataProvider(seed=9).get_candles(symbol="BTCUSDT", timeframe="1h", limit=10)
    runner = WalkForwardRunner(
        candles=candles,
        strategy_class=BuyAndHoldStrategy,
        param_grid={"symbol": ["BTCUSDT"]},
        initial_capital=10000.0,
        risk_limit=1000.0,
        periods_per_year=252,
        initial_train_size=200,
        out_of_sample_size=50,
    )

    assert runner.run() == []
