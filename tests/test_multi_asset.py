from tradingbot.backtest.multi_asset import MultiAssetResearchRunner, fetch_multi_asset_candles
from tradingbot.backtest.trade_ledger import extract_closed_trades
from tradingbot.data.models import MarketCandle
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy


class _RecordingParamsStrategy(Strategy):
    """Test-Doppel: speichert die erhaltenen Konstruktor-Parameter öffentlich."""

    def __init__(self, **kwargs):
        self.params = kwargs

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        return TradingSignal(symbol=symbol, signal="HOLD", confidence=0.0)


class _BuyThenSellOnceStrategy(Strategy):
    """Test-Doppel: kauft beim ersten `analyze()`-Aufruf, verkauft beim
    zweiten, danach nur noch HOLD. Symbol wird aus den Kerzen gelesen (kein
    Konstruktor-Parameter) - dadurch mit identischen Parametern über
    mehrere Assets verwendbar.
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


# --- fetch_multi_asset_candles -------------------------------------------------------


def test_fetch_multi_asset_candles_returns_one_series_per_symbol():

    provider = SimulatedDataProvider(seed=1)

    result = fetch_multi_asset_candles(
        provider, symbols=["BTCUSDT", "ETHUSDT", "AAPL"], timeframe="1h", limit=20
    )

    assert set(result.keys()) == {"BTCUSDT", "ETHUSDT", "AAPL"}
    for symbol, candles in result.items():
        assert len(candles) == 20
        assert all(c.symbol == symbol for c in candles)


def test_fetch_multi_asset_candles_different_symbols_have_different_data():

    provider = SimulatedDataProvider(seed=1)

    result = fetch_multi_asset_candles(
        provider, symbols=["BTCUSDT", "ETHUSDT"], timeframe="1h", limit=10
    )

    btc_closes = [c.close for c in result["BTCUSDT"]]
    eth_closes = [c.close for c in result["ETHUSDT"]]
    assert btc_closes != eth_closes


# --- MultiAssetResearchRunner ---------------------------------------------------------


def test_multi_asset_research_runner_returns_result_per_symbol():

    candles_by_symbol = fetch_multi_asset_candles(
        SimulatedDataProvider(seed=2), symbols=["BTCUSDT", "ETHUSDT"], timeframe="1h", limit=20
    )
    runner = MultiAssetResearchRunner(
        candles_by_symbol=candles_by_symbol, initial_capital=10000.0, risk_limit=1000.0
    )

    results = runner.run(MovingAverageCrossoverStrategy, {"short_window": 2, "long_window": 5})

    assert set(results.keys()) == {"BTCUSDT", "ETHUSDT"}
    for result in results.values():
        assert len(result.cycle_results) == 19
        assert len(result.equity_curve) == 19


def test_multi_asset_research_runner_uses_identical_parameters_for_all_assets():

    candles_by_symbol = fetch_multi_asset_candles(
        SimulatedDataProvider(seed=3),
        symbols=["BTCUSDT", "ETHUSDT", "AAPL"],
        timeframe="1h",
        limit=10,
    )
    runner = MultiAssetResearchRunner(
        candles_by_symbol=candles_by_symbol, initial_capital=10000.0, risk_limit=500.0
    )

    seen_params = []

    class _CapturingStrategy(_RecordingParamsStrategy):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            seen_params.append(kwargs)

    runner.run(_CapturingStrategy, {"a": 1, "b": "x"})

    assert len(seen_params) == 3
    assert all(params == {"a": 1, "b": "x"} for params in seen_params)


def test_multi_asset_research_runner_applies_same_strategy_logic_independently():

    candles_by_symbol = fetch_multi_asset_candles(
        SimulatedDataProvider(seed=9), symbols=["BTCUSDT", "ETHUSDT"], timeframe="1h", limit=20
    )
    runner = MultiAssetResearchRunner(
        candles_by_symbol=candles_by_symbol, initial_capital=10000.0, risk_limit=1000.0
    )

    results = runner.run(MovingAverageCrossoverStrategy, {"short_window": 2, "long_window": 5})

    # Dieselbe Strategie-Logik, unabhaengig auf jedem Asset vollstaendig
    # berechnet - beide Ergebnisse sind eigenstaendig und vollstaendig.
    for symbol, result in results.items():
        assert isinstance(result.profit_loss, float)
        assert len(result.equity_curve) == 19
        assert all(c.symbol == symbol for c in candles_by_symbol[symbol])


def test_multi_asset_research_runner_isolates_strategy_state_between_assets():

    candles_by_symbol = fetch_multi_asset_candles(
        SimulatedDataProvider(seed=5),
        symbols=["BTCUSDT", "ETHUSDT", "AAPL"],
        timeframe="1h",
        limit=10,
    )
    runner = MultiAssetResearchRunner(
        candles_by_symbol=candles_by_symbol, initial_capital=10000.0, risk_limit=1000.0
    )

    results = runner.run(_BuyThenSellOnceStrategy, {})

    # Jede frische Instanz durchlaeuft BUY -> SELL -> HOLD* unabhaengig -
    # waere Zustand zwischen Assets geteilt, haetten die spaeter verarbeiteten
    # Assets keinen abgeschlossenen Trade mehr (BUY/SELL bereits "verbraucht").
    for symbol, result in results.items():
        closed_trades = extract_closed_trades(result.cycle_results)
        assert len(closed_trades) == 1, f"{symbol}: erwartete genau 1 abgeschlossenen Trade"
