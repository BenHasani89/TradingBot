import pytest

from tradingbot.portfolio.manager import PortfolioManager


def test_portfolio_add_position():

    portfolio = PortfolioManager(initial_capital=10000)

    portfolio.add_position(
        symbol="BTC",
        quantity=0.5,
        price=60000,
    )

    status = portfolio.status()

    assert len(status.positions) == 1
    assert status.positions[0].symbol == "BTC"


def test_apply_trade_buy_deducts_capital_and_creates_position():

    portfolio = PortfolioManager(initial_capital=10000)

    portfolio.apply_trade(
        symbol="BTC",
        side="BUY",
        quantity=0.1,
        price=60000,
    )

    status = portfolio.status()

    assert status.capital == pytest.approx(4000)
    assert len(status.positions) == 1
    assert status.positions[0].symbol == "BTC"
    assert status.positions[0].quantity == pytest.approx(0.1)
    assert status.positions[0].entry_price == pytest.approx(60000)


def test_apply_trade_buy_increases_existing_position_with_average_price():

    portfolio = PortfolioManager(initial_capital=100000)

    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=0.1, price=60000)
    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=0.1, price=62000)

    status = portfolio.status()

    assert len(status.positions) == 1
    assert status.positions[0].quantity == pytest.approx(0.2)
    assert status.positions[0].entry_price == pytest.approx(61000)


def test_apply_trade_sell_reduces_position_and_credits_capital():

    portfolio = PortfolioManager(initial_capital=10000)
    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=0.2, price=60000)

    portfolio.apply_trade(symbol="BTC", side="SELL", quantity=0.1, price=61000)

    status = portfolio.status()

    assert len(status.positions) == 1
    assert status.positions[0].quantity == pytest.approx(0.1)
    assert status.capital == pytest.approx(10000 - 0.2 * 60000 + 0.1 * 61000)


def test_apply_trade_sell_full_quantity_removes_position():

    portfolio = PortfolioManager(initial_capital=10000)
    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=0.1, price=60000)

    portfolio.apply_trade(symbol="BTC", side="SELL", quantity=0.1, price=61000)

    status = portfolio.status()

    assert status.positions == []
