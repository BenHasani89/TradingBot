from datetime import UTC, datetime

import pytest

from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import PaperBroker
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.simple import SimpleStrategy


def _candles(previous_close: float, current_close: float, symbol: str = "BTCUSDT"):

    return [
        MarketCandle(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            open=previous_close,
            high=previous_close,
            low=previous_close,
            close=previous_close,
            volume=1000,
        ),
        MarketCandle(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            open=current_close,
            high=current_close,
            low=current_close,
            close=current_close,
            volume=1000,
        ),
    ]


def _build_orchestrator(initial_capital: float = 10000.0, max_position_size: float = 1000.0):

    engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=max_position_size),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    return engine, portfolio, orchestrator


def test_run_cycle_raises_when_engine_not_running():

    _, _, orchestrator = _build_orchestrator()

    with pytest.raises(RuntimeError):
        orchestrator.run_cycle(_candles(100, 110))


def test_run_cycle_executes_buy_and_updates_portfolio():

    engine, portfolio, orchestrator = _build_orchestrator(
        initial_capital=10000.0,
        max_position_size=1000.0,
    )
    engine.start()

    result = orchestrator.run_cycle(_candles(100, 110))

    assert result.signal.signal == "BUY"
    assert result.decision.approved is True
    assert result.order is not None
    assert result.order.side == "BUY"
    assert result.order.quantity == pytest.approx(1000.0 / 110.0)
    assert result.execution is not None
    assert result.execution.success is True

    status = portfolio.status()
    assert status.capital == pytest.approx(10000.0 - 1000.0)
    assert len(status.positions) == 1
    assert status.positions[0].symbol == "BTCUSDT"
    assert status.positions[0].quantity == pytest.approx(1000.0 / 110.0)


def test_run_cycle_does_not_trade_on_hold_signal():

    engine, portfolio, orchestrator = _build_orchestrator()
    engine.start()

    # Gleicher Schlusskurs -> SimpleStrategy liefert HOLD.
    result = orchestrator.run_cycle(_candles(100, 100))

    assert result.signal.signal == "HOLD"
    assert result.decision.approved is False
    assert result.order is None
    assert result.execution is None

    status = portfolio.status()
    assert status.capital == pytest.approx(10000.0)
    assert status.positions == []
