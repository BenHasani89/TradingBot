from datetime import date

from tradingbot.portfolio.models import PortfolioStatus, Position
from tradingbot.portfolio.persistence import SqlitePortfolioRepository
from tradingbot.risk.persistence import SqliteRiskStateRepository
from tradingbot.risk.repository import RiskStateRepository
from tradingbot.risk.risk_state import RiskState


def _repository(tmp_path) -> SqliteRiskStateRepository:

    return SqliteRiskStateRepository(str(tmp_path / "trading.sqlite3"))


def _state() -> RiskState:

    return RiskState(
        day_start_equity=9500.0,
        day_start_date=date(2026, 7, 18),
        peak_equity=10500.0,
        kill_switch_active=True,
        kill_switch_reason="Max Drawdown überschritten: 25.00% (Limit 20.00%)",
        daily_loss_blocked=False,
        daily_loss_reason=None,
    )


# --- Grundverhalten ---------------------------------------------------------------------------


def test_sqlite_repository_is_a_risk_state_repository(tmp_path):

    assert isinstance(_repository(tmp_path), RiskStateRepository)


def test_load_without_prior_save_returns_none(tmp_path):

    repository = _repository(tmp_path)

    assert repository.load("default") is None


def test_save_and_load_roundtrip(tmp_path):

    repository = _repository(tmp_path)
    state = _state()

    repository.save("default", state)
    loaded = repository.load("default")

    assert loaded == state


def test_save_overwrites_previous_state_completely(tmp_path):

    repository = _repository(tmp_path)
    repository.save("default", _state())

    updated = RiskState(
        day_start_equity=11000.0,
        day_start_date=date(2026, 7, 19),
        peak_equity=11000.0,
        kill_switch_active=False,
        kill_switch_reason=None,
        daily_loss_blocked=True,
        daily_loss_reason="Daily Loss Limit überschritten: 6.00% (Limit 5.00%)",
    )
    repository.save("default", updated)

    loaded = repository.load("default")

    assert loaded == updated


def test_different_risk_ids_are_isolated(tmp_path):

    repository = _repository(tmp_path)
    repository.save("a", _state())
    repository.save(
        "b",
        RiskState(day_start_equity=1.0, day_start_date=date(2026, 1, 1), peak_equity=1.0),
    )

    assert repository.load("a").kill_switch_active is True
    assert repository.load("b").kill_switch_active is False


# --- Gemeinsame SQLite-Datei mit dem Portfolio-Repository -------------------------------------


def test_shares_db_file_with_portfolio_repository_without_interference(tmp_path):

    db_path = str(tmp_path / "trading.sqlite3")
    portfolio_repository = SqlitePortfolioRepository(db_path)
    risk_repository = SqliteRiskStateRepository(db_path)

    portfolio_repository.save(
        "default",
        PortfolioStatus(
            capital=4000.0,
            positions=[Position(symbol="BTC", quantity=0.1, entry_price=60000.0)],
        ),
    )
    risk_repository.save("default", _state())

    loaded_portfolio = portfolio_repository.load("default")
    loaded_risk = risk_repository.load("default")

    assert loaded_portfolio.capital == 4000.0
    assert loaded_risk.kill_switch_active is True
