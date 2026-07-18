from datetime import UTC, datetime

from tradingbot.paper_trading.audit import AuditEventType, SqliteAuditLog


def _log(tmp_path) -> SqliteAuditLog:

    return SqliteAuditLog(str(tmp_path / "trading.sqlite3"))


def test_record_returns_and_persists_event(tmp_path):

    log = _log(tmp_path)
    now = datetime(2026, 7, 18, 12, tzinfo=UTC)

    event = log.record("session-1", AuditEventType.SESSION_STARTED, "Session gestartet", now=now)

    assert event.session_id == "session-1"
    assert event.event_type == AuditEventType.SESSION_STARTED
    assert event.timestamp == now


def test_for_session_returns_events_in_chronological_order(tmp_path):

    log = _log(tmp_path)
    log.record(
        "session-1", AuditEventType.SESSION_STARTED, "Start", now=datetime(2026, 7, 18, tzinfo=UTC)
    )
    log.record(
        "session-1",
        AuditEventType.ORDER_EXECUTED,
        "BUY 0.1 BTCUSDT",
        now=datetime(2026, 7, 18, 1, tzinfo=UTC),
    )
    log.record(
        "session-1",
        AuditEventType.SESSION_STOPPED,
        "Stop",
        now=datetime(2026, 7, 18, 2, tzinfo=UTC),
    )

    events = log.for_session("session-1")

    assert [e.event_type for e in events] == [
        AuditEventType.SESSION_STARTED,
        AuditEventType.ORDER_EXECUTED,
        AuditEventType.SESSION_STOPPED,
    ]


def test_for_session_filters_by_session_id(tmp_path):

    log = _log(tmp_path)
    log.record("session-1", AuditEventType.SESSION_STARTED, "A")
    log.record("session-2", AuditEventType.SESSION_STARTED, "B")

    assert len(log.for_session("session-1")) == 1


def test_for_session_without_events_returns_empty_list(tmp_path):

    log = _log(tmp_path)

    assert log.for_session("unknown") == []
