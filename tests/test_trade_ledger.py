from datetime import UTC, datetime

import pytest

from tradingbot.backtest.trade_ledger import (
    average_loss,
    average_trade,
    average_win,
    extract_closed_trades,
    payoff_ratio,
    profit_factor,
    win_rate_percent,
)
from tradingbot.core.engine import TradingEngine
from tradingbot.core.models import TradingCycleResult
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import PaperBroker
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.portfolio.models import ClosedTrade
from tradingbot.risk.manager import RiskManager
from tradingbot.risk.models import RiskDecision
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal

# --- PortfolioManager.apply_trade: ClosedTrade-Erzeugung --------------------------


def test_buy_does_not_produce_closed_trade():

    portfolio = PortfolioManager(initial_capital=10000.0)

    result = portfolio.apply_trade(symbol="BTC", side="BUY", quantity=1.0, price=100.0)

    assert result is None


def test_sell_produces_closed_trade_with_correct_values():

    portfolio = PortfolioManager(initial_capital=10000.0)
    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=1.0, price=100.0)

    closed_trade = portfolio.apply_trade(symbol="BTC", side="SELL", quantity=1.0, price=150.0)

    assert closed_trade is not None
    assert closed_trade.symbol == "BTC"
    assert closed_trade.quantity == 1.0
    assert closed_trade.entry_price == 100.0
    assert closed_trade.exit_price == 150.0
    assert closed_trade.profit_loss == pytest.approx(50.0)


def test_sell_produces_negative_profit_loss_for_loss():

    portfolio = PortfolioManager(initial_capital=10000.0)
    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=2.0, price=100.0)

    closed_trade = portfolio.apply_trade(symbol="BTC", side="SELL", quantity=2.0, price=80.0)

    assert closed_trade.profit_loss == pytest.approx(-40.0)


def test_sell_without_existing_position_returns_none():

    portfolio = PortfolioManager(initial_capital=10000.0)

    closed_trade = portfolio.apply_trade(symbol="BTC", side="SELL", quantity=1.0, price=100.0)

    assert closed_trade is None


def test_partial_sell_uses_weighted_average_entry_price():

    portfolio = PortfolioManager(initial_capital=100000.0)
    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=1.0, price=100.0)
    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=1.0, price=200.0)
    # gewichteter Durchschnitt: 150.0

    closed_trade = portfolio.apply_trade(symbol="BTC", side="SELL", quantity=1.0, price=180.0)

    assert closed_trade.entry_price == pytest.approx(150.0)
    assert closed_trade.profit_loss == pytest.approx(30.0)


# --- TradingOrchestrator: closed_trade wird weitergereicht -------------------------


class _BuyThenSellStrategy(Strategy):
    """Test-Doppel: erstes Signal BUY, danach immer SELL."""

    def __init__(self) -> None:
        self._has_bought = False

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        symbol = candles[-1].symbol if candles else "UNKNOWN"
        if not self._has_bought:
            self._has_bought = True
            return TradingSignal(symbol=symbol, signal="BUY", confidence=1.0)
        return TradingSignal(symbol=symbol, signal="SELL", confidence=1.0)


def _candles(price: float, symbol: str = "BTCUSDT", count: int = 2):

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


def _build_orchestrator(strategy, initial_capital: float, max_position_size: float):

    engine = TradingEngine()
    engine.start()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=engine,
        strategy=strategy,
        risk_manager=RiskManager(max_position_size=max_position_size),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    return portfolio, orchestrator


def test_orchestrator_buy_cycle_has_no_closed_trade():

    portfolio, orchestrator = _build_orchestrator(
        _BuyThenSellStrategy(), initial_capital=10000.0, max_position_size=1000.0
    )

    result = orchestrator.run_cycle(_candles(price=100.0))

    assert result.closed_trade is None


def test_orchestrator_sell_cycle_produces_closed_trade():

    portfolio, orchestrator = _build_orchestrator(
        _BuyThenSellStrategy(), initial_capital=10000.0, max_position_size=1000.0
    )

    orchestrator.run_cycle(_candles(price=100.0))  # BUY: quantity = 1000/100 = 10
    result = orchestrator.run_cycle(_candles(price=120.0))  # SELL: quantity = 1000/120

    sold_quantity = 1000.0 / 120.0
    expected_profit_loss = (120.0 - 100.0) * sold_quantity

    assert result.closed_trade is not None
    assert result.closed_trade.symbol == "BTCUSDT"
    assert result.closed_trade.quantity == pytest.approx(sold_quantity)
    assert result.closed_trade.entry_price == pytest.approx(100.0)
    assert result.closed_trade.exit_price == pytest.approx(120.0)
    assert result.closed_trade.profit_loss == pytest.approx(expected_profit_loss)


# --- backtest/trade_ledger.py: extract_closed_trades --------------------------------


def _cycle_result(closed_trade: ClosedTrade | None) -> TradingCycleResult:

    return TradingCycleResult(
        signal=TradingSignal(symbol="BTC", signal="SELL", confidence=1.0),
        decision=RiskDecision(approved=True, position_size=100.0, reason="ok"),
        order=None,
        execution=None,
        closed_trade=closed_trade,
    )


def _trade(profit_loss: float, entry_price: float = 100.0, quantity: float = 1.0) -> ClosedTrade:

    return ClosedTrade(
        symbol="BTC",
        quantity=quantity,
        entry_price=entry_price,
        exit_price=entry_price + profit_loss / quantity,
        profit_loss=profit_loss,
    )


def test_extract_closed_trades_filters_none():

    cycle_results = [
        _cycle_result(_trade(10.0)),
        _cycle_result(None),
        _cycle_result(_trade(-5.0)),
    ]

    extracted = extract_closed_trades(cycle_results)

    assert len(extracted) == 2
    assert extracted[0].profit_loss == 10.0
    assert extracted[1].profit_loss == -5.0


def test_extract_closed_trades_empty_list():

    assert extract_closed_trades([]) == []


# --- Kennzahlen-Funktionen ----------------------------------------------------------


def test_win_rate_percent_correct():

    trades = [_trade(50.0), _trade(-20.0), _trade(30.0), _trade(-10.0)]

    assert win_rate_percent(trades) == pytest.approx(50.0)


def test_win_rate_percent_empty_is_zero():

    assert win_rate_percent([]) == 0.0


def test_average_win_correct():

    trades = [_trade(50.0), _trade(-20.0), _trade(30.0)]

    assert average_win(trades) == pytest.approx(40.0)


def test_average_win_no_wins_is_zero():

    assert average_win([_trade(-10.0)]) == 0.0


def test_average_loss_correct():

    trades = [_trade(50.0), _trade(-20.0), _trade(-40.0)]

    assert average_loss(trades) == pytest.approx(-30.0)


def test_average_loss_no_losses_is_zero():

    assert average_loss([_trade(10.0)]) == 0.0


def test_profit_factor_correct():

    trades = [_trade(50.0), _trade(-20.0), _trade(30.0), _trade(-10.0)]

    assert profit_factor(trades) == pytest.approx(80.0 / 30.0)


def test_profit_factor_no_losses_is_infinite():

    trades = [_trade(50.0), _trade(30.0)]

    assert profit_factor(trades) == float("inf")


def test_profit_factor_empty_is_zero():

    assert profit_factor([]) == 0.0


def test_average_trade_correct():

    trades = [_trade(50.0), _trade(-20.0), _trade(30.0), _trade(-10.0)]

    assert average_trade(trades) == pytest.approx(12.5)  # (50-20+30-10)/4


def test_average_trade_empty_is_zero():

    assert average_trade([]) == 0.0


def test_payoff_ratio_correct():

    trades = [_trade(60.0), _trade(-20.0), _trade(30.0), _trade(-10.0)]
    # average_win = (60+30)/2 = 45, average_loss = (-20-10)/2 = -15
    # payoff_ratio = 45 / 15 = 3.0

    assert payoff_ratio(trades) == pytest.approx(3.0)


def test_payoff_ratio_no_losses_is_infinite():

    trades = [_trade(50.0), _trade(30.0)]

    assert payoff_ratio(trades) == float("inf")


def test_payoff_ratio_no_wins_is_zero():

    trades = [_trade(-10.0), _trade(-20.0)]

    assert payoff_ratio(trades) == 0.0
