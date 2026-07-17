from datetime import UTC, datetime

import pytest

from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import PaperBroker
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal


class _AlwaysBuyStrategy(Strategy):
    """Test-Doppel, das immer ein BUY-Signal mit hoher Konfidenz liefert."""

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        return TradingSignal(symbol=symbol, signal="BUY", confidence=1.0)


def _candles(price: float = 100.0, symbol: str = "BTCUSDT", count: int = 2):

    now = datetime.now(UTC)
    return [
        MarketCandle(
            symbol=symbol,
            timestamp=now,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000,
        )
        for _ in range(count)
    ]


def _build_orchestrator(initial_capital: float, max_position_size: float):

    engine = TradingEngine()
    engine.start()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=_AlwaysBuyStrategy(),
        risk_manager=RiskManager(max_position_size=max_position_size),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    return portfolio, orchestrator


def test_buy_rejected_when_capital_insufficient():

    # Positionsgroesse 1000, Kerzenpreis 100 -> benoetigt 1000, aber nur 100 verfuegbar.
    portfolio, orchestrator = _build_orchestrator(initial_capital=100.0, max_position_size=1000.0)

    result = orchestrator.run_cycle(_candles(price=100.0))

    assert result.order is None
    assert result.execution is None
    assert portfolio.available_cash() == 100.0
    assert portfolio.status().positions == []


def test_capital_never_goes_negative_across_multiple_cycles():

    # Erster Kauf (100) ist leistbar, danach reicht das verbleibende Kapital (50) nicht mehr.
    portfolio, orchestrator = _build_orchestrator(initial_capital=150.0, max_position_size=100.0)

    for _ in range(5):
        orchestrator.run_cycle(_candles(price=100.0))
        assert portfolio.available_cash() >= 0.0

    assert portfolio.available_cash() == pytest.approx(50.0)


def test_normal_buy_still_works_when_capital_sufficient():

    portfolio, orchestrator = _build_orchestrator(
        initial_capital=10000.0, max_position_size=1000.0
    )

    result = orchestrator.run_cycle(_candles(price=100.0))

    assert result.order is not None
    assert result.execution is not None
    assert result.execution.success is True
    assert portfolio.available_cash() == pytest.approx(10000.0 - 1000.0)
    assert len(portfolio.status().positions) == 1


def test_available_cash_reflects_initial_capital():

    portfolio = PortfolioManager(initial_capital=5000.0)

    assert portfolio.available_cash() == 5000.0


def test_available_cash_updates_after_trade():

    portfolio = PortfolioManager(initial_capital=5000.0)
    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=0.1, price=1000.0)

    assert portfolio.available_cash() == pytest.approx(4900.0)
