from datetime import UTC, datetime

from tradingbot.paper_trading.order_history import OrderExecution, SqliteOrderHistory


def _history(tmp_path) -> SqliteOrderHistory:

    return SqliteOrderHistory(str(tmp_path / "trading.sqlite3"))


def _execution(close: float = 100.0, success: bool = True) -> OrderExecution:

    return OrderExecution(
        timestamp=datetime(2026, 7, 18, 12, tzinfo=UTC),
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.1,
        price=close,
        fee=0.5,
        success=success,
    )


def test_latest_without_prior_append_returns_none(tmp_path):

    assert _history(tmp_path).latest("session-1") is None


def test_all_without_prior_append_returns_empty_list(tmp_path):

    assert _history(tmp_path).all("session-1") == []


def test_append_and_latest_roundtrip(tmp_path):

    history = _history(tmp_path)
    execution = _execution()

    history.append("session-1", execution)

    assert history.latest("session-1") == execution


def test_append_is_additive_not_overwriting(tmp_path):

    history = _history(tmp_path)
    history.append("session-1", _execution(close=100.0))
    history.append("session-1", _execution(close=110.0))

    all_executions = history.all("session-1")

    assert len(all_executions) == 2
    assert [e.price for e in all_executions] == [100.0, 110.0]


def test_latest_returns_most_recently_appended(tmp_path):

    history = _history(tmp_path)
    history.append("session-1", _execution(close=100.0))
    history.append("session-1", _execution(close=110.0))

    assert history.latest("session-1").price == 110.0


def test_records_failed_execution_with_success_false(tmp_path):

    history = _history(tmp_path)
    history.append("session-1", _execution(success=False))

    assert history.latest("session-1").success is False


def test_different_session_ids_are_isolated(tmp_path):

    history = _history(tmp_path)
    history.append("session-1", _execution())

    assert history.all("session-2") == []
    assert history.latest("session-2") is None
