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
