from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.backtest.capital_allocation import CapitalAllocator
from tradingbot.backtest.metrics import max_drawdown_percent, performance_percent, sharpe_ratio
from tradingbot.backtest.portfolio_engine import PortfolioBacktestEngine
from tradingbot.backtest.trade_ledger import extract_closed_trades
from tradingbot.data.models import MarketCandle
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy


def _flat_candles(price: float, count: int, symbol: str) -> list[MarketCandle]:

    now = datetime.now(UTC)
    return [
        MarketCandle(
            symbol=symbol,
            timestamp=now + timedelta(hours=i),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000,
        )
        for i in range(count)
    ]


class _AlwaysBuyStrategy(Strategy):
    """Test-Doppel: immer BUY. Kein Konstruktor-Parameter, Symbol wird aus
    den Kerzen gelesen - dadurch mit identischen Parametern über mehrere
    Assets verwendbar.
    """

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        return TradingSignal(symbol=symbol, signal="BUY", confidence=1.0)


class _BuyThenSellOnceStrategy(Strategy):
    """Test-Doppel: kauft beim ersten Aufruf, verkauft beim zweiten, danach
    nur noch HOLD. Kein Konstruktor-Parameter.
    """

    def __init__(self) -> None:
        self._step = 0

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        self._step += 1
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        if self._step == 1:
            return TradingSignal(symbol=symbol, signal="BUY", confidence=1.0)
        if self._step == 2:
            return TradingSignal(symbol=symbol, signal="SELL", confidence=1.0)
        return TradingSignal(symbol=symbol, signal="HOLD", confidence=0.0)


class _RecordingStrategy(Strategy):
    """Test-Doppel: protokolliert je Instanz die gesehenen Fensterlängen."""

    instances: list["_RecordingStrategy"] = []

    def __init__(self) -> None:
        self.seen_lengths: list[int] = []
        _RecordingStrategy.instances.append(self)

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        self.seen_lengths.append(len(candles))
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        return TradingSignal(symbol=symbol, signal="HOLD", confidence=0.0)


# --- Kapitalverteilung ---------------------------------------------------------------


def test_portfolio_engine_allocates_capital_equally_across_assets():

    candles_by_symbol = {
        "BTCUSDT": _flat_candles(100.0, 6, "BTCUSDT"),
        "ETHUSDT": _flat_candles(100.0, 6, "ETHUSDT"),
        "AAPL": _flat_candles(100.0, 6, "AAPL"),
    }
    engine = PortfolioBacktestEngine(
        candles_by_symbol=candles_by_symbol,
        strategy_class=_AlwaysBuyStrategy,
        strategy_params={},
        initial_capital=9000.0,
        allocator=CapitalAllocator(),
    )

    result = engine.run()

    assert result.allocation == {"BTCUSDT": 3000.0, "ETHUSDT": 3000.0, "AAPL": 3000.0}


# --- Gemeinsames Portfolio statt getrennte Konten -------------------------------------


def test_portfolio_engine_uses_single_shared_equity_curve_for_all_assets():

    candles_by_symbol = {
        "BTCUSDT": _flat_candles(100.0, 10, "BTCUSDT"),
        "ETHUSDT": _flat_candles(50.0, 10, "ETHUSDT"),
    }
    engine = PortfolioBacktestEngine(
        candles_by_symbol=candles_by_symbol,
        strategy_class=_AlwaysBuyStrategy,
        strategy_params={},
        initial_capital=10000.0,
        allocator=CapitalAllocator(),
    )

    result = engine.run()

    # Genau EINE Equity-Kurve fuer das gesamte Portfolio (nicht eine je Asset).
    assert len(result.equity_curve) == 9

    # Beide Assets haben tatsaechlich aus demselben Kapitaltopf gehandelt.
    btc_cycles = result.cycle_results_by_symbol["BTCUSDT"]
    eth_cycles = result.cycle_results_by_symbol["ETHUSDT"]
    btc_trades = [c for c in btc_cycles if c.execution and c.execution.success]
    eth_trades = [c for c in eth_cycles if c.execution and c.execution.success]
    assert len(btc_trades) >= 1
    assert len(eth_trades) >= 1


# --- Strategie-Isolation zwischen Assets -----------------------------------------------


def test_portfolio_engine_isolates_strategy_state_between_assets():

    candles_by_symbol = {
        "BTCUSDT": _flat_candles(100.0, 6, "BTCUSDT"),
        "ETHUSDT": _flat_candles(100.0, 6, "ETHUSDT"),
        "AAPL": _flat_candles(100.0, 6, "AAPL"),
    }
    engine = PortfolioBacktestEngine(
        candles_by_symbol=candles_by_symbol,
        strategy_class=_BuyThenSellOnceStrategy,
        strategy_params={},
        initial_capital=3000.0,
        allocator=CapitalAllocator(),
    )

    result = engine.run()

    for symbol, cycles in result.cycle_results_by_symbol.items():
        closed_trades = extract_closed_trades(cycles)
        assert len(closed_trades) == 1, f"{symbol}: erwartete genau 1 abgeschlossenen Trade"


# --- Synchronisierte Zeitschritte -------------------------------------------------------


def test_portfolio_engine_synchronizes_time_steps_across_assets():

    _RecordingStrategy.instances = []

    candles_by_symbol = {
        "BTCUSDT": _flat_candles(100.0, 8, "BTCUSDT"),
        "ETHUSDT": _flat_candles(100.0, 8, "ETHUSDT"),
    }
    engine = PortfolioBacktestEngine(
        candles_by_symbol=candles_by_symbol,
        strategy_class=_RecordingStrategy,
        strategy_params={},
        initial_capital=1000.0,
        allocator=CapitalAllocator(),
    )

    engine.run()

    assert len(_RecordingStrategy.instances) == 2  # eine frische Instanz je Asset

    # Fenstergroesse waechst exakt um eins pro Schritt (2..8) - synchron
    # und identisch fuer beide Assets, kein Blick in die Zukunft.
    for instance in _RecordingStrategy.instances:
        assert instance.seen_lengths == list(range(2, 9))


# --- Portfolio Equity Curve --------------------------------------------------------------


def test_portfolio_engine_equity_curve_matches_synchronized_timestamps():

    candles_by_symbol = {
        "BTCUSDT": _flat_candles(100.0, 6, "BTCUSDT"),
        "ETHUSDT": _flat_candles(100.0, 6, "ETHUSDT"),
    }
    engine = PortfolioBacktestEngine(
        candles_by_symbol=candles_by_symbol,
        strategy_class=_AlwaysBuyStrategy,
        strategy_params={},
        initial_capital=1000.0,
        allocator=CapitalAllocator(),
    )

    result = engine.run()

    assert len(result.equity_curve) == 5
    expected_timestamps = [c.timestamp for c in candles_by_symbol["BTCUSDT"][1:]]
    actual_timestamps = [p.timestamp for p in result.equity_curve]
    assert actual_timestamps == expected_timestamps


# --- Performance-Metriken auf der Portfolio-Equity-Kurve --------------------------------


def test_portfolio_equity_curve_works_with_existing_metrics_functions():

    candles_by_symbol = {
        "BTCUSDT": SimulatedDataProvider(seed=1).get_candles(
            symbol="BTCUSDT", timeframe="1h", limit=20
        ),
        "ETHUSDT": SimulatedDataProvider(seed=2).get_candles(
            symbol="ETHUSDT", timeframe="1h", limit=20
        ),
    }
    engine = PortfolioBacktestEngine(
        candles_by_symbol=candles_by_symbol,
        strategy_class=MovingAverageCrossoverStrategy,
        strategy_params={"short_window": 2, "long_window": 5},
        initial_capital=10000.0,
        allocator=CapitalAllocator(),
    )

    result = engine.run()

    assert result.performance_percent == pytest.approx(
        performance_percent(10000.0, result.equity_curve)
    )
    assert result.max_drawdown_percent == pytest.approx(
        max_drawdown_percent(result.equity_curve)
    )
    # Weitere bestehende Metrik-Funktionen (nicht Teil von PortfolioBacktestResult)
    # laufen unveraendert auf der Portfolio-Equity-Kurve.
    sharpe = sharpe_ratio(result.equity_curve, periods_per_year=24 * 365)
    assert isinstance(sharpe, float)


# --- Kein Kapital-Leak zwischen Assets ---------------------------------------------------


def test_portfolio_engine_no_asset_spends_beyond_its_allocation():

    candles_by_symbol = {
        "BTCUSDT": _flat_candles(100.0, 5, "BTCUSDT"),
        "ETHUSDT": _flat_candles(100.0, 5, "ETHUSDT"),
        "AAPL": _flat_candles(100.0, 5, "AAPL"),
    }
    engine = PortfolioBacktestEngine(
        candles_by_symbol=candles_by_symbol,
        strategy_class=_AlwaysBuyStrategy,
        strategy_params={},
        initial_capital=300.0,
        allocator=CapitalAllocator(),
    )

    result = engine.run()

    for symbol, cycles in result.cycle_results_by_symbol.items():
        allocated = result.allocation[symbol]
        for cycle in cycles:
            if cycle.execution is not None and cycle.execution.success:
                cost = cycle.execution.order.price * cycle.execution.order.quantity
                assert cost <= allocated + 1e-6

    # Zusaetzliche Kapital-Erhaltungspruefung: das Portfolio kann insgesamt
    # nie mehr verlieren, als eingesetzt wurde.
    assert result.profit_loss >= -300.0


def test_portfolio_engine_total_allocation_never_exceeds_initial_capital():

    candles_by_symbol = {
        "BTCUSDT": _flat_candles(100.0, 5, "BTCUSDT"),
        "ETHUSDT": _flat_candles(100.0, 5, "ETHUSDT"),
        "AAPL": _flat_candles(100.0, 5, "AAPL"),
    }
    engine = PortfolioBacktestEngine(
        candles_by_symbol=candles_by_symbol,
        strategy_class=_AlwaysBuyStrategy,
        strategy_params={},
        initial_capital=9999.0,
        allocator=CapitalAllocator(),
    )

    result = engine.run()

    assert sum(result.allocation.values()) == pytest.approx(9999.0)


# --- Randfaelle ---------------------------------------------------------------------------


def test_portfolio_engine_no_assets_returns_empty_result():

    engine = PortfolioBacktestEngine(
        candles_by_symbol={},
        strategy_class=_AlwaysBuyStrategy,
        strategy_params={},
        initial_capital=1000.0,
        allocator=CapitalAllocator(),
    )

    result = engine.run()

    assert result.equity_curve == []
    assert result.trades == 0
    assert result.profit_loss == 0.0
