from datetime import UTC, datetime

import pytest

from tradingbot.cli import commands
from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.market import MarketDataStore
from tradingbot.data.models import MarketCandle
from tradingbot.data.provider import DataProvider
from tradingbot.execution.broker import PaperBroker
from tradingbot.paper_trading.audit import SqliteAuditLog
from tradingbot.paper_trading.engine import PaperTradingEngine
from tradingbot.paper_trading.health import HealthSnapshot
from tradingbot.paper_trading.order_history import SqliteOrderHistory
from tradingbot.paper_trading.persistence import SqliteSessionRepository
from tradingbot.paper_trading.scheduler import SimpleLoopScheduler
from tradingbot.paper_trading.session import SessionMetadata, create_session
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.portfolio.persistence import SqlitePortfolioRepository
from tradingbot.risk.manager import RiskManager
from tradingbot.risk.persistence import SqliteRiskStateRepository
from tradingbot.strategy.simple import SimpleStrategy


class _EmptyProvider(DataProvider):
    """Liefert nie Kerzen - hält `run_cycle_once()` in Tests trivial."""

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[MarketCandle]:
        return []


def _build_engine(tmp_path) -> PaperTradingEngine:

    db_path = str(tmp_path / "trading.sqlite3")
    trading_engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=10000.0)
    orchestrator = TradingOrchestrator(
        engine=trading_engine,
        strategy=SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=PaperBroker(),
    )
    session = create_session(symbol="BTCUSDT", timeframe="1h", strategy_name="SimpleStrategy")

    return PaperTradingEngine(
        engine=trading_engine,
        provider=_EmptyProvider(),
        store=MarketDataStore(),
        orchestrator=orchestrator,
        portfolio=portfolio,
        portfolio_repository=SqlitePortfolioRepository(db_path),
        risk_repository=SqliteRiskStateRepository(db_path),
        session=session,
        session_repository=SqliteSessionRepository(db_path),
        audit_log=SqliteAuditLog(db_path),
        order_history=SqliteOrderHistory(db_path),
        symbol="BTCUSDT",
        timeframe="1h",
        candle_limit=5,
        max_daily_loss_percent=100.0,
        max_drawdown_percent=100.0,
        max_exposure_percent=100.0,
        max_exposure_per_asset_percent=100.0,
    )


# --- run_start --------------------------------------------------------------------------------


def test_run_start_executes_at_least_one_cycle_and_stops_cleanly(tmp_path):

    engine = _build_engine(tmp_path)
    scheduler = SimpleLoopScheduler(sleep=lambda _seconds: scheduler.stop())

    exit_code = commands.run_start(engine, scheduler, interval_seconds=0.0)

    assert exit_code == 0
    assert engine.session.status == "stopped"


def test_run_start_stops_engine_even_if_scheduler_raises(tmp_path):

    engine = _build_engine(tmp_path)

    class _BrokenScheduler:
        def run(self, callback, interval_seconds: float) -> None:
            raise RuntimeError("boom")

        def stop(self) -> None:
            pass

    with pytest.raises(RuntimeError, match="boom"):
        commands.run_start(engine, _BrokenScheduler(), interval_seconds=0.0)

    assert engine.session.status == "stopped"


# --- format_status ------------------------------------------------------------------------


def test_format_status_unknown_session_returns_exit_code_1():

    text, exit_code = commands.format_status(None, "unknown-id")

    assert exit_code == 1
    assert "unknown-id" in text


def test_format_status_known_session_returns_exit_code_0():

    session = SessionMetadata(
        session_id="session-1",
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="SimpleStrategy",
        started_at=datetime(2026, 7, 18, tzinfo=UTC),
        status="running",
    )

    text, exit_code = commands.format_status(session, "session-1")

    assert exit_code == 0
    assert "session-1" in text
    assert "running" in text


# --- format_health --------------------------------------------------------------------------


def test_format_health_unknown_session_returns_exit_code_1():

    text, exit_code = commands.format_health(None, "unknown-id")

    assert exit_code == 1
    assert "unknown-id" in text


def test_format_health_known_snapshot_returns_exit_code_0():

    snapshot = HealthSnapshot(
        session_id="session-1",
        engine_running=False,
        heartbeat_at=None,
        last_candle_timestamp=None,
        last_order=None,
        last_error=None,
        risk_state=None,
    )

    text, exit_code = commands.format_health(snapshot, "session-1")

    assert exit_code == 0
    assert "session-1" in text
    assert "immer False" in text
    assert "keine Candle-Persistenz" in text


# --- format_sessions ------------------------------------------------------------------------


def test_format_sessions_empty_list_returns_exit_code_0():

    text, exit_code = commands.format_sessions([])

    assert exit_code == 0
    assert "Keine Sessions" in text


def test_format_sessions_lists_all_sessions():

    sessions = [
        SessionMetadata(
            session_id="session-1",
            symbol="BTCUSDT",
            timeframe="1h",
            strategy_name="SimpleStrategy",
            started_at=datetime(2026, 7, 18, tzinfo=UTC),
        ),
        SessionMetadata(
            session_id="session-2",
            symbol="ETHUSDT",
            timeframe="1h",
            strategy_name="SimpleStrategy",
            started_at=datetime(2026, 7, 18, tzinfo=UTC),
        ),
    ]

    text, exit_code = commands.format_sessions(sessions)

    assert exit_code == 0
    assert "session-1" in text
    assert "session-2" in text
