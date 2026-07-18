from datetime import UTC, datetime

from tradingbot.paper_trading.persistence import SqliteSessionRepository
from tradingbot.paper_trading.repository import SessionRepository
from tradingbot.paper_trading.session import SessionMetadata


def _repository(tmp_path) -> SqliteSessionRepository:

    return SqliteSessionRepository(str(tmp_path / "trading.sqlite3"))


def _session() -> SessionMetadata:

    return SessionMetadata(
        session_id="session-1",
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="SimpleStrategy",
        started_at=datetime(2026, 7, 18, 12, tzinfo=UTC),
    )


def test_sqlite_repository_is_a_session_repository(tmp_path):

    assert isinstance(_repository(tmp_path), SessionRepository)


def test_load_without_prior_save_returns_none(tmp_path):

    assert _repository(tmp_path).load("unknown") is None


def test_save_and_load_roundtrip(tmp_path):

    repository = _repository(tmp_path)
    session = _session()

    repository.save(session)

    assert repository.load("session-1") == session


def test_save_persists_stopped_session(tmp_path):

    repository = _repository(tmp_path)
    session = _session()
    session.status = "stopped"
    session.stopped_at = datetime(2026, 7, 18, 13, tzinfo=UTC)

    repository.save(session)
    loaded = repository.load("session-1")

    assert loaded.status == "stopped"
    assert loaded.stopped_at == datetime(2026, 7, 18, 13, tzinfo=UTC)


def test_save_overwrites_previous_state_for_same_session_id(tmp_path):

    repository = _repository(tmp_path)
    repository.save(_session())

    updated = _session()
    updated.status = "stopped"
    repository.save(updated)

    assert repository.load("session-1").status == "stopped"


# --- all() ------------------------------------------------------------------------------------


def test_all_without_any_saved_session_returns_empty_list(tmp_path):

    assert _repository(tmp_path).all() == []


def test_all_returns_every_saved_session(tmp_path):

    repository = _repository(tmp_path)
    first = _session()
    second = SessionMetadata(
        session_id="session-2",
        symbol="ETHUSDT",
        timeframe="1h",
        strategy_name="SimpleStrategy",
        started_at=datetime(2026, 7, 18, 13, tzinfo=UTC),
    )
    repository.save(first)
    repository.save(second)

    all_sessions = repository.all()

    assert {s.session_id for s in all_sessions} == {"session-1", "session-2"}


def test_all_is_ordered_by_started_at_ascending(tmp_path):

    repository = _repository(tmp_path)
    later = SessionMetadata(
        session_id="later",
        symbol="ETHUSDT",
        timeframe="1h",
        strategy_name="SimpleStrategy",
        started_at=datetime(2026, 7, 19, tzinfo=UTC),
    )
    earlier = SessionMetadata(
        session_id="earlier",
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="SimpleStrategy",
        started_at=datetime(2026, 7, 17, tzinfo=UTC),
    )
    repository.save(later)
    repository.save(earlier)

    all_sessions = repository.all()

    assert [s.session_id for s in all_sessions] == ["earlier", "later"]


def test_all_reflects_overwrite_not_duplicate_entries(tmp_path):

    repository = _repository(tmp_path)
    repository.save(_session())
    updated = _session()
    updated.status = "stopped"
    repository.save(updated)

    all_sessions = repository.all()

    assert len(all_sessions) == 1
    assert all_sessions[0].status == "stopped"
