import math
import statistics
from datetime import UTC, datetime

import pytest

from tradingbot.backtest.engine import BacktestEngine
from tradingbot.backtest.metrics import (
    annualized_return_percent,
    calmar_ratio,
    max_drawdown_percent,
    performance_percent,
    sharpe_ratio,
    volatility_percent,
)
from tradingbot.backtest.models import EquityPoint
from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.execution.broker import PaperBroker
from tradingbot.execution.order_repository import InMemoryOrderRepository
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.simple import SimpleStrategy


class _RecordingStrategy(Strategy):
    """Test-Doppel, das nur die Fensterlängen protokolliert, die es sieht."""

    def __init__(self) -> None:
        self.seen_lengths: list[int] = []

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        self.seen_lengths.append(len(candles))
        return TradingSignal(symbol=candles[-1].symbol, signal="HOLD", confidence=0.0)


def _build_engine(strategy, symbol="BTCUSDT", candle_count=10, initial_capital=10000.0):

    engine = TradingEngine()
    engine.start()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=strategy,
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    candles = SimulatedDataProvider(seed=3).get_candles(
        symbol=symbol, timeframe="1h", limit=candle_count
    )
    backtest = BacktestEngine(
        orchestrator=orchestrator,
        portfolio=portfolio,
        symbol=symbol,
        candles=candles,
    )
    return backtest, portfolio, candles


def test_backtest_full_run_returns_result():

    backtest, _, candles = _build_engine(SimpleStrategy(), candle_count=10)

    result = backtest.run()

    assert len(result.cycle_results) == len(candles) - 1
    assert len(result.equity_curve) == len(candles) - 1
    assert isinstance(result.trades, int)
    assert isinstance(result.profit_loss, float)
    assert isinstance(result.performance_percent, float)
    assert isinstance(result.max_drawdown_percent, float)


def test_backtest_orchestrator_without_order_repository_stays_in_memory():
    """Backtest-Aufrufer übergeben `order_repository` nicht (siehe
    `_build_engine` oben, identisch zu `backtest/research.py` und
    `backtest/portfolio_engine.py`) - der TradingOrchestrator muss dabei
    weiterhin automatisch beim In-Memory-Standard bleiben, ohne jede
    SQLite-Interaktion."""

    backtest, _, _ = _build_engine(SimpleStrategy(), candle_count=10)

    assert isinstance(backtest._orchestrator._order_manager._repository, InMemoryOrderRepository)

    result = backtest.run()

    assert result.trades >= 0  # Backtest läuft unverändert vollständig durch.


def test_backtest_no_lookahead_bias():

    strategy = _RecordingStrategy()
    backtest, _, candles = _build_engine(strategy, candle_count=8)

    backtest.run()

    # Fenstergroesse waechst exakt um eins pro Schritt (2, 3, ..., N) -
    # die Strategie sieht nie mehr Kerzen, als zu diesem Zeitpunkt bekannt
    # waeren, und keine wird uebersprungen.
    assert strategy.seen_lengths == list(range(2, len(candles) + 1))


def test_backtest_equity_curve_matches_candle_timestamps():

    backtest, _, candles = _build_engine(SimpleStrategy(), candle_count=6)

    result = backtest.run()

    expected_timestamps = [c.timestamp for c in candles[1:]]
    actual_timestamps = [p.timestamp for p in result.equity_curve]

    assert actual_timestamps == expected_timestamps


def test_backtest_profit_loss_matches_final_equity():

    backtest, _, _ = _build_engine(SimpleStrategy(), candle_count=15, initial_capital=10000.0)

    result = backtest.run()

    expected_profit_loss = result.equity_curve[-1].total_value - 10000.0
    assert result.profit_loss == pytest.approx(expected_profit_loss)


def test_backtest_trades_count_matches_successful_executions():

    backtest, _, _ = _build_engine(SimpleStrategy(), candle_count=15)

    result = backtest.run()

    expected_trades = sum(
        1
        for cycle in result.cycle_results
        if cycle.execution is not None and cycle.execution.success
    )
    assert result.trades == expected_trades


def test_performance_percent_positive_return():

    curve = [EquityPoint(timestamp=datetime.now(UTC), total_value=11000.0)]

    assert performance_percent(10000.0, curve) == pytest.approx(10.0)


def test_performance_percent_empty_curve_is_zero():

    assert performance_percent(10000.0, []) == 0.0


def test_max_drawdown_percent_computes_largest_decline():

    now = datetime.now(UTC)
    curve = [
        EquityPoint(timestamp=now, total_value=10000.0),
        EquityPoint(timestamp=now, total_value=12000.0),
        EquityPoint(timestamp=now, total_value=9000.0),
        EquityPoint(timestamp=now, total_value=11000.0),
    ]

    assert max_drawdown_percent(curve) == pytest.approx(25.0)


def test_max_drawdown_percent_empty_curve_is_zero():

    assert max_drawdown_percent([]) == 0.0


def test_volatility_percent_known_series():

    now = datetime.now(UTC)
    curve = [
        EquityPoint(timestamp=now, total_value=100.0),
        EquityPoint(timestamp=now, total_value=110.0),
        EquityPoint(timestamp=now, total_value=99.0),
    ]
    # Renditen: +0.10, -0.10 (exakt, da 110 * 0.9 = 99) -> Stichproben-
    # Standardabweichung unabhaengig von der Produktionsfunktion nachgerechnet.
    expected = math.sqrt(0.02) * 100

    assert volatility_percent(curve, periods_per_year=1) == pytest.approx(expected)


def test_volatility_percent_too_few_points_is_zero():

    now = datetime.now(UTC)
    curve = [EquityPoint(timestamp=now, total_value=100.0)]

    assert volatility_percent(curve, periods_per_year=252) == 0.0
    assert volatility_percent([], periods_per_year=252) == 0.0


def test_sharpe_ratio_known_series():

    now = datetime.now(UTC)
    values = [100.0, 120.0, 108.0, 118.8]
    curve = [EquityPoint(timestamp=now, total_value=v) for v in values]
    returns = [
        (values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))
    ]
    expected = statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(1)

    assert sharpe_ratio(curve, periods_per_year=1) == pytest.approx(expected)


def test_sharpe_ratio_zero_volatility_is_zero():

    now = datetime.now(UTC)
    # Jede Periode exakt +10% -> keine Schwankung der Renditen.
    curve = [
        EquityPoint(timestamp=now, total_value=100.0),
        EquityPoint(timestamp=now, total_value=110.0),
        EquityPoint(timestamp=now, total_value=121.0),
        EquityPoint(timestamp=now, total_value=133.1),
    ]

    assert sharpe_ratio(curve, periods_per_year=1) == 0.0


def test_sharpe_ratio_too_few_points_is_zero():

    now = datetime.now(UTC)
    curve = [EquityPoint(timestamp=now, total_value=100.0)]

    assert sharpe_ratio(curve, periods_per_year=252) == 0.0
    assert sharpe_ratio([], periods_per_year=252) == 0.0


def test_sharpe_ratio_risk_free_rate_lowers_ratio():

    now = datetime.now(UTC)
    values = [100.0, 120.0, 108.0, 118.8]
    curve = [EquityPoint(timestamp=now, total_value=v) for v in values]

    without_rf = sharpe_ratio(curve, periods_per_year=1, risk_free_rate=0.0)
    with_rf = sharpe_ratio(curve, periods_per_year=1, risk_free_rate=0.05)

    assert with_rf < without_rf


def test_annualized_return_percent_matches_total_return_for_one_year():

    now = datetime.now(UTC)
    curve = [
        EquityPoint(timestamp=now, total_value=1025.0),
        EquityPoint(timestamp=now, total_value=1050.0),
        EquityPoint(timestamp=now, total_value=1075.0),
        EquityPoint(timestamp=now, total_value=1100.0),
    ]

    result = annualized_return_percent(curve, initial_capital=1000.0, periods_per_year=4)

    assert result == pytest.approx(10.0)


def test_annualized_return_percent_compounds_over_multiple_years():

    now = datetime.now(UTC)
    values = [1050, 1100, 1150, 1200, 1205, 1207, 1209, 1210]
    curve = [EquityPoint(timestamp=now, total_value=float(v)) for v in values]

    # 8 Perioden bei periods_per_year=4 -> 2 Jahre; Gesamtrendite 21% -> 10% p.a.
    result = annualized_return_percent(curve, initial_capital=1000.0, periods_per_year=4)

    assert result == pytest.approx(10.0, rel=1e-6)


def test_annualized_return_percent_empty_curve_is_zero():

    assert annualized_return_percent([], initial_capital=1000.0, periods_per_year=252) == 0.0


def test_calmar_ratio_correct():

    now = datetime.now(UTC)
    curve = [
        EquityPoint(timestamp=now, total_value=1000.0),
        EquityPoint(timestamp=now, total_value=950.0),
        EquityPoint(timestamp=now, total_value=1100.0),
    ]

    # 1 Jahr (3 Perioden, periods_per_year=3): Gesamtrendite 10% -> annualisiert 10%.
    # Max Drawdown: (1000-950)/1000 = 5%. Calmar = 10/5 = 2.0.
    result = calmar_ratio(curve, initial_capital=1000.0, periods_per_year=3)

    assert result == pytest.approx(2.0)


def test_calmar_ratio_no_drawdown_with_positive_return_is_infinite():

    now = datetime.now(UTC)
    curve = [
        EquityPoint(timestamp=now, total_value=1000.0),
        EquityPoint(timestamp=now, total_value=1050.0),
        EquityPoint(timestamp=now, total_value=1100.0),
    ]

    result = calmar_ratio(curve, initial_capital=1000.0, periods_per_year=3)

    assert result == float("inf")


def test_calmar_ratio_no_drawdown_no_return_is_zero():

    now = datetime.now(UTC)
    curve = [
        EquityPoint(timestamp=now, total_value=1000.0),
        EquityPoint(timestamp=now, total_value=1000.0),
    ]

    result = calmar_ratio(curve, initial_capital=1000.0, periods_per_year=2)

    assert result == 0.0
