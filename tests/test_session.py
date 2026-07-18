from datetime import UTC, datetime

from tradingbot.paper_trading.session import SessionMetadata, create_session


def test_create_session_generates_uuid_and_defaults():

    session = create_session(symbol="BTCUSDT", timeframe="1h", strategy_name="SimpleStrategy")

    assert len(session.session_id) == 36  # UUID4-Format
    assert session.symbol == "BTCUSDT"
    assert session.status == "running"
    assert session.stopped_at is None


def test_create_session_accepts_explicit_now():

    now = datetime(2026, 7, 18, 12, tzinfo=UTC)

    session = create_session(
        symbol="BTCUSDT", timeframe="1h", strategy_name="SimpleStrategy", now=now
    )

    assert session.started_at == now


def test_session_metadata_is_a_plain_dataclass():

    session = SessionMetadata(
        session_id="abc",
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="SimpleStrategy",
        started_at=datetime(2026, 7, 18, tzinfo=UTC),
    )

    assert session.status == "running"
    assert session.stopped_at is None
