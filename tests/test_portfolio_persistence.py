import pytest

from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.portfolio.models import PortfolioStatus, Position
from tradingbot.portfolio.persistence import SqlitePortfolioRepository
from tradingbot.portfolio.repository import PortfolioRepository


def _repository(tmp_path) -> SqlitePortfolioRepository:

    return SqlitePortfolioRepository(str(tmp_path / "portfolio.sqlite3"))


# --- Repository: Grundverhalten -------------------------------------------------------------


def test_sqlite_repository_is_a_portfolio_repository(tmp_path):

    assert isinstance(_repository(tmp_path), PortfolioRepository)


def test_load_without_prior_save_returns_none(tmp_path):

    repository = _repository(tmp_path)

    assert repository.load("default") is None


def test_save_and_load_roundtrip(tmp_path):

    repository = _repository(tmp_path)
    state = PortfolioStatus(
        capital=4000.0,
        positions=[Position(symbol="BTC", quantity=0.1, entry_price=60000.0)],
    )

    repository.save("default", state)
    loaded = repository.load("default")

    assert loaded == state


def test_save_overwrites_previous_state_completely(tmp_path):

    repository = _repository(tmp_path)
    repository.save(
        "default",
        PortfolioStatus(
            capital=1000.0,
            positions=[Position(symbol="BTC", quantity=1.0, entry_price=100.0)],
        ),
    )

    repository.save(
        "default",
        PortfolioStatus(
            capital=2000.0,
            positions=[Position(symbol="ETH", quantity=2.0, entry_price=200.0)],
        ),
    )

    loaded = repository.load("default")

    assert loaded.capital == pytest.approx(2000.0)
    assert loaded.positions == [Position(symbol="ETH", quantity=2.0, entry_price=200.0)]


def test_different_portfolio_ids_are_isolated(tmp_path):

    repository = _repository(tmp_path)
    repository.save("a", PortfolioStatus(capital=100.0, positions=[]))
    repository.save("b", PortfolioStatus(capital=200.0, positions=[]))

    assert repository.load("a").capital == pytest.approx(100.0)
    assert repository.load("b").capital == pytest.approx(200.0)


# --- Restart-Simulation: PortfolioManager -> speichern -> neuer PortfolioManager -> laden -----


def test_restart_simulation_restores_identical_state(tmp_path):

    repository = _repository(tmp_path)

    original = PortfolioManager(initial_capital=10000)
    original.apply_trade(symbol="BTC", side="BUY", quantity=0.2, price=60000)
    original.apply_trade(symbol="ETH", side="BUY", quantity=1.0, price=3000)
    original.apply_trade(symbol="BTC", side="SELL", quantity=0.1, price=61000)

    repository.save("default", original.export_state())

    restarted = PortfolioManager(initial_capital=0)
    restored_state = repository.load("default")
    restarted.restore_state(restored_state)

    assert restarted.status() == original.status()


def test_restored_positions_can_be_reduced_and_closed(tmp_path):

    repository = _repository(tmp_path)

    original = PortfolioManager(initial_capital=10000)
    original.apply_trade(symbol="BTC", side="BUY", quantity=0.2, price=60000)
    repository.save("default", original.export_state())

    restarted = PortfolioManager(initial_capital=0)
    restarted.restore_state(repository.load("default"))

    closed_trade = restarted.apply_trade(symbol="BTC", side="SELL", quantity=0.2, price=62000)

    assert closed_trade is not None
    assert closed_trade.profit_loss == pytest.approx((62000 - 60000) * 0.2)
    assert restarted.status().positions == []


def test_old_codepath_without_persistence_still_works(tmp_path):

    portfolio = PortfolioManager(initial_capital=10000)

    portfolio.apply_trade(symbol="BTC", side="BUY", quantity=0.1, price=60000)
    status = portfolio.status()

    assert status.capital == pytest.approx(4000)
    assert len(status.positions) == 1
