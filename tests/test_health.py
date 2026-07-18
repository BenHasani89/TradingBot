from datetime import UTC, date, datetime

from tradingbot.core.engine import TradingEngine
from tradingbot.data.market import MarketDataStore
from tradingbot.data.models import MarketCandle
from tradingbot.execution.models import ExecutionStatus
from tradingbot.paper_trading.health import build_health_snapshot
from tradingbot.paper_trading.order_history import OrderExecution, SqliteOrderHistory
from tradingbot.paper_trading.session import SessionMetadata
from tradingbot.risk.risk_state import RiskState

SYMBOL = "BTCUSDT"


def _session() -> SessionMetadata:

    return SessionMetadata(
        session_id="session-1",
        symbol=SYMBOL,
        timeframe="1h",
        strategy_name="SimpleStrategy",
        started_at=datetime(2026, 7, 18, tzinfo=UTC),
        heartbeat_at=datetime(2026, 7, 18, 12, tzinfo=UTC),
    )


def _risk_state() -> RiskState:

    return RiskState(
        day_start_equity=10000.0, day_start_date=date(2026, 7, 18), peak_equity=10000.0
    )


def test_snapshot_reflects_engine_running_state(tmp_path):

    trading_engine = TradingEngine()
    trading_engine.start()

    snapshot = build_health_snapshot(
        session=_session(),
        trading_engine=trading_engine,
        store=MarketDataStore(),
        symbol=SYMBOL,
        order_history=SqliteOrderHistory(str(tmp_path / "trading.sqlite3")),
        risk_state=_risk_state(),
        last_error=None,
    )

    assert snapshot.engine_running is True


def test_snapshot_reflects_engine_stopped_state(tmp_path):

    trading_engine = TradingEngine()

    snapshot = build_health_snapshot(
        session=_session(),
        trading_engine=trading_engine,
        store=MarketDataStore(),
        symbol=SYMBOL,
        order_history=SqliteOrderHistory(str(tmp_path / "trading.sqlite3")),
        risk_state=None,
        last_error=None,
    )

    assert snapshot.engine_running is False
    assert snapshot.risk_state is None


def test_snapshot_includes_last_candle_timestamp(tmp_path):

    store = MarketDataStore()
    timestamp = datetime(2026, 7, 18, 12, tzinfo=UTC)
    store.add(
        MarketCandle(
            symbol=SYMBOL, timestamp=timestamp, open=100, high=100, low=100, close=100,
            volume=1000,
        )
    )

    snapshot = build_health_snapshot(
        session=_session(),
        trading_engine=TradingEngine(),
        store=store,
        symbol=SYMBOL,
        order_history=SqliteOrderHistory(str(tmp_path / "trading.sqlite3")),
        risk_state=None,
        last_error=None,
    )

    assert snapshot.last_candle_timestamp == timestamp


def test_snapshot_without_candles_has_none_timestamp(tmp_path):

    snapshot = build_health_snapshot(
        session=_session(),
        trading_engine=TradingEngine(),
        store=MarketDataStore(),
        symbol=SYMBOL,
        order_history=SqliteOrderHistory(str(tmp_path / "trading.sqlite3")),
        risk_state=None,
        last_error=None,
    )

    assert snapshot.last_candle_timestamp is None


def test_snapshot_includes_latest_order_from_history(tmp_path):

    db_path = str(tmp_path / "trading.sqlite3")
    order_history = SqliteOrderHistory(db_path)
    order_history.append(
        "session-1",
        OrderExecution(
            timestamp=datetime(2026, 7, 18, 12, tzinfo=UTC),
            symbol=SYMBOL,
            side="BUY",
            quantity=0.1,
            price=60000.0,
            fee=0.5,
            success=True,
            client_order_id="client-1",
            broker_order_id="client-1",
            status=ExecutionStatus.SUCCESS,
        ),
    )

    snapshot = build_health_snapshot(
        session=_session(),
        trading_engine=TradingEngine(),
        store=MarketDataStore(),
        symbol=SYMBOL,
        order_history=order_history,
        risk_state=None,
        last_error=None,
    )

    assert snapshot.last_order is not None
    assert snapshot.last_order.symbol == SYMBOL


def test_snapshot_carries_through_heartbeat_and_last_error(tmp_path):

    session = _session()

    snapshot = build_health_snapshot(
        session=session,
        trading_engine=TradingEngine(),
        store=MarketDataStore(),
        symbol=SYMBOL,
        order_history=SqliteOrderHistory(str(tmp_path / "trading.sqlite3")),
        risk_state=None,
        last_error="Fehler in Phase 'data_provider': Netzwerkfehler",
    )

    assert snapshot.heartbeat_at == session.heartbeat_at
    assert snapshot.last_error == "Fehler in Phase 'data_provider': Netzwerkfehler"
