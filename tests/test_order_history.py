import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tradingbot.execution.models import ExecutionStatus
from tradingbot.paper_trading.order_history import OrderExecution, SqliteOrderHistory


def _history(tmp_path) -> SqliteOrderHistory:

    return SqliteOrderHistory(str(tmp_path / "trading.sqlite3"))


def _execution(
    close: float = 100.0,
    success: bool = True,
    client_order_id: str | None = None,
    broker_order_id: str | None = None,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
) -> OrderExecution:

    return OrderExecution(
        timestamp=datetime(2026, 7, 18, 12, tzinfo=UTC),
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.1,
        price=close,
        fee=0.5,
        success=success,
        client_order_id=client_order_id if client_order_id is not None else str(uuid4()),
        broker_order_id=broker_order_id,
        status=status,
    )


def test_latest_without_prior_append_returns_none(tmp_path):

    assert _history(tmp_path).latest("session-1") is None


def test_all_without_prior_append_returns_empty_list(tmp_path):

    assert _history(tmp_path).all("session-1") == []


def test_append_and_latest_roundtrip(tmp_path):

    history = _history(tmp_path)
    execution = _execution(broker_order_id="broker-1")

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
    history.append("session-1", _execution(success=False, status=ExecutionStatus.FAILED))

    latest = history.latest("session-1")
    assert latest.success is False
    assert latest.status == ExecutionStatus.FAILED


def test_records_unknown_status(tmp_path):

    history = _history(tmp_path)
    history.append("session-1", _execution(success=False, status=ExecutionStatus.UNKNOWN))

    assert history.latest("session-1").status == ExecutionStatus.UNKNOWN


def test_different_session_ids_are_isolated(tmp_path):

    history = _history(tmp_path)
    history.append("session-1", _execution())

    assert history.all("session-2") == []
    assert history.latest("session-2") is None


# --- Duplicate Detection (client_order_id) -----------------------------------------------


def test_append_with_duplicate_client_order_id_raises(tmp_path):

    history = _history(tmp_path)
    execution = _execution(client_order_id="same-id")

    history.append("session-1", execution)

    with pytest.raises(sqlite3.IntegrityError):
        history.append("session-1", _execution(client_order_id="same-id", close=200.0))

    # Kein zweiter Eintrag entstanden - die Order wurde nicht doppelt verbucht.
    assert len(history.all("session-1")) == 1
