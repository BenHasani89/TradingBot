from datetime import UTC, datetime, timedelta

import pytest

from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.market import MarketDataStore
from tradingbot.data.models import MarketCandle
from tradingbot.data.provider import DataProvider
from tradingbot.execution.broker import Broker, PaperBroker
from tradingbot.execution.models import ExecutionResult, Order
from tradingbot.paper_trading.audit import AuditEventType, SqliteAuditLog
from tradingbot.paper_trading.engine import PaperTradingEngine
from tradingbot.paper_trading.order_history import SqliteOrderHistory
from tradingbot.paper_trading.persistence import SqliteSessionRepository
from tradingbot.paper_trading.session import create_session
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.portfolio.persistence import SqlitePortfolioRepository
from tradingbot.risk.manager import RiskManager
from tradingbot.risk.persistence import SqliteRiskStateRepository
from tradingbot.risk.risk_state import RiskState
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.models import TradingSignal
from tradingbot.strategy.simple import SimpleStrategy

SYMBOL = "BTCUSDT"


class _Clock:

    def __init__(self, current: datetime):
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class _FixedCandleProvider(DataProvider):
    """Liefert vordefinierte Kerzen-Batches, ein Batch je Aufruf - macht
    Testfälle unabhängig von der Nicht-Kontinuität des
    `SimulatedDataProvider`."""

    def __init__(self, batches: list[list[MarketCandle]]):
        self._batches = batches
        self.calls = 0

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[MarketCandle]:
        self.calls += 1
        if self.calls > len(self._batches):
            return []
        return self._batches[self.calls - 1]


def _candle(timestamp: datetime, close: float) -> MarketCandle:

    return MarketCandle(
        symbol=SYMBOL, timestamp=timestamp, open=close, high=close, low=close,
        close=close, volume=1000,
    )


class _FailingProvider(DataProvider):
    """Wirft bei jedem Aufruf - simuliert einen DataProvider-Fehler."""

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[MarketCandle]:
        raise ConnectionError("Netzwerkfehler beim Datenabruf")


class _FailingStrategy(Strategy):
    """Wirft bei jeder Analyse - simuliert einen Strategie-Fehler."""

    def analyze(self, candles: list[MarketCandle]) -> TradingSignal:
        raise ValueError("Strategie-Bug")


class _FailingBroker(Broker):
    """Wirft bei jeder Ausführung - simuliert einen Broker-Fehler."""

    def execute(self, order: Order) -> ExecutionResult:
        raise RuntimeError("Broker nicht erreichbar")


def _build_engine(
    tmp_path,
    provider: DataProvider,
    clock: _Clock,
    max_daily_loss_percent: float = 100.0,
    max_drawdown_percent: float = 100.0,
    max_exposure_percent: float = 100.0,
    max_exposure_per_asset_percent: float = 100.0,
    db_path: str | None = None,
    session_id: str = "session-1",
    initial_capital: float = 10000.0,
    strategy: Strategy | None = None,
    broker: Broker | None = None,
):
    db_path = db_path if db_path is not None else str(tmp_path / "trading.sqlite3")

    trading_engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    orchestrator = TradingOrchestrator(
        engine=trading_engine,
        strategy=strategy if strategy is not None else SimpleStrategy(),
        risk_manager=RiskManager(max_position_size=1000.0),
        portfolio=portfolio,
        broker=broker if broker is not None else PaperBroker(),
    )
    session = create_session(
        symbol=SYMBOL, timeframe="1h", strategy_name="SimpleStrategy", now=clock.current
    )
    session.session_id = session_id

    engine = PaperTradingEngine(
        engine=trading_engine,
        provider=provider,
        store=MarketDataStore(),
        orchestrator=orchestrator,
        portfolio=portfolio,
        portfolio_repository=SqlitePortfolioRepository(db_path),
        risk_repository=SqliteRiskStateRepository(db_path),
        session=session,
        session_repository=SqliteSessionRepository(db_path),
        audit_log=SqliteAuditLog(db_path),
        order_history=SqliteOrderHistory(db_path),
        symbol=SYMBOL,
        timeframe="1h",
        candle_limit=5,
        max_daily_loss_percent=max_daily_loss_percent,
        max_drawdown_percent=max_drawdown_percent,
        max_exposure_percent=max_exposure_percent,
        max_exposure_per_asset_percent=max_exposure_per_asset_percent,
        now=clock,
    )
    return engine, trading_engine, portfolio, db_path


# --- start() ----------------------------------------------------------------------------------


def test_start_bootstraps_fresh_risk_state_when_none_persisted(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    engine, _, _, _ = _build_engine(tmp_path, _FixedCandleProvider([]), clock)

    engine.start()

    assert engine.risk_guard.state.day_start_equity == 10000.0
    assert engine.risk_guard.state.peak_equity == 10000.0
    assert engine.risk_guard.state.kill_switch_active is False


def test_start_records_session_started_audit_event(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    engine, _, _, _ = _build_engine(tmp_path, _FixedCandleProvider([]), clock, db_path=db_path)

    engine.start()

    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[0].event_type == AuditEventType.SESSION_STARTED


def test_start_persists_session_metadata(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    engine, _, _, _ = _build_engine(tmp_path, _FixedCandleProvider([]), clock, db_path=db_path)

    engine.start()

    loaded = SqliteSessionRepository(db_path).load("session-1")
    assert loaded is not None
    assert loaded.symbol == SYMBOL


def test_start_loads_previously_persisted_kill_switch(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    SqliteRiskStateRepository(db_path).save(
        "session-1",
        RiskState(
            day_start_equity=9000.0,
            day_start_date=clock.current.date(),
            peak_equity=10000.0,
            kill_switch_active=True,
            kill_switch_reason="Max Drawdown überschritten",
        ),
    )
    engine, _, _, _ = _build_engine(tmp_path, _FixedCandleProvider([]), clock, db_path=db_path)

    engine.start()

    assert engine.risk_guard.state.kill_switch_active is True


# --- run_cycle_once(): Blockade-Fälle ohne Orchestrator-Aufruf --------------------------------


def test_run_cycle_once_returns_none_when_engine_not_running(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    provider = _FixedCandleProvider([])
    engine, trading_engine, _, _ = _build_engine(tmp_path, provider, clock)
    engine.start()
    trading_engine.stop()

    result = engine.run_cycle_once()

    assert result is None
    assert provider.calls == 0


def test_run_cycle_once_blocks_on_active_kill_switch_without_fetching_data(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    SqliteRiskStateRepository(db_path).save(
        "session-1",
        RiskState(
            day_start_equity=10000.0,
            day_start_date=clock.current.date(),
            peak_equity=10000.0,
            kill_switch_active=True,
            kill_switch_reason="Test",
        ),
    )
    provider = _FixedCandleProvider([[_candle(clock.current, 100.0)]])
    engine, _, _, _ = _build_engine(tmp_path, provider, clock, db_path=db_path)
    engine.start()

    result = engine.run_cycle_once()

    assert result is None
    assert provider.calls == 0
    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[-1].event_type == AuditEventType.TRADE_BLOCKED
    assert "Kill-Switch" in events[-1].message


def test_run_cycle_once_returns_none_when_no_genuinely_new_candle(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    t1 = clock.current
    t2 = t1 + timedelta(hours=1)
    same_batch = [_candle(t1, 100.0), _candle(t2, 110.0)]
    provider = _FixedCandleProvider([same_batch, same_batch])
    engine, _, _, _ = _build_engine(tmp_path, provider, clock)
    engine.start()

    engine.run_cycle_once()
    result = engine.run_cycle_once()

    assert result is None
    assert provider.calls == 2


def test_run_cycle_once_blocked_by_exposure_limit_does_not_call_orchestrator(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    t1 = clock.current
    t2 = t1 + timedelta(hours=1)
    t3 = t1 + timedelta(hours=2)
    provider = _FixedCandleProvider(
        [[_candle(t1, 100.0), _candle(t2, 110.0)], [_candle(t3, 120.0)]]
    )
    db_path = str(tmp_path / "trading.sqlite3")
    engine, _, portfolio, _ = _build_engine(
        tmp_path,
        provider,
        clock,
        max_exposure_percent=1.0,
        max_exposure_per_asset_percent=50.0,
        db_path=db_path,
    )
    engine.start()

    engine.run_cycle_once()  # baut eine Position auf (BUY, 110 > 100)
    positions_after_first_cycle = list(portfolio.status().positions)

    engine.run_cycle_once()  # zweiter Zyklus: Exposure bereits über 1% -> blockiert

    assert portfolio.status().positions == positions_after_first_cycle
    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[-1].event_type == AuditEventType.TRADE_BLOCKED
    assert "Exposure" in events[-1].message


# --- run_cycle_once(): erfolgreicher Zyklus ----------------------------------------------------


def test_run_cycle_once_executes_trade_and_persists_state(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    t1 = clock.current
    t2 = t1 + timedelta(hours=1)
    provider = _FixedCandleProvider([[_candle(t1, 100.0), _candle(t2, 110.0)]])
    db_path = str(tmp_path / "trading.sqlite3")
    engine, _, portfolio, _ = _build_engine(tmp_path, provider, clock, db_path=db_path)
    engine.start()

    result = engine.run_cycle_once()

    assert result is not None
    assert result.execution is not None
    assert result.execution.success is True
    assert len(portfolio.status().positions) == 1

    saved_portfolio = SqlitePortfolioRepository(db_path).load("session-1")
    assert saved_portfolio.capital == portfolio.status().capital

    events = SqliteAuditLog(db_path).for_session("session-1")
    assert any(e.event_type == AuditEventType.ORDER_EXECUTED for e in events)


# --- stop() -------------------------------------------------------------------------------------


def test_stop_persists_final_state_and_records_reason(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    engine, trading_engine, _, _ = _build_engine(
        tmp_path, _FixedCandleProvider([]), clock, db_path=db_path
    )
    engine.start()

    engine.stop(reason="Betreiber-Stopp")

    assert trading_engine.status()["running"] is False
    session = SqliteSessionRepository(db_path).load("session-1")
    assert session.status == "stopped"
    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[-1].event_type == AuditEventType.SESSION_STOPPED
    assert events[-1].message == "Betreiber-Stopp"


# --- Neustart-Simulation --------------------------------------------------------------------


def test_restart_simulation_resumes_with_identical_portfolio_and_risk_state(tmp_path):

    db_path = str(tmp_path / "trading.sqlite3")
    clock1 = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    t1 = clock1.current
    t2 = t1 + timedelta(hours=1)
    provider1 = _FixedCandleProvider([[_candle(t1, 100.0), _candle(t2, 110.0)]])

    engine1, _, portfolio1, _ = _build_engine(tmp_path, provider1, clock1, db_path=db_path)
    engine1.start()
    engine1.run_cycle_once()
    engine1.stop()

    clock2 = _Clock(datetime(2026, 7, 19, 9, tzinfo=UTC))
    engine2, _, portfolio2, _ = _build_engine(
        tmp_path, _FixedCandleProvider([]), clock2, db_path=db_path
    )
    engine2.start()

    assert portfolio2.status() == portfolio1.status()
    assert engine2.risk_guard.state.peak_equity == engine1.risk_guard.state.peak_equity


# --- Heartbeat ----------------------------------------------------------------------------------


def test_run_cycle_once_updates_and_persists_heartbeat(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    engine, _, _, _ = _build_engine(
        tmp_path, _FixedCandleProvider([[]]), clock, db_path=db_path
    )
    engine.start()

    engine.run_cycle_once()

    assert engine.session.heartbeat_at == clock.current
    loaded = SqliteSessionRepository(db_path).load("session-1")
    assert loaded.heartbeat_at == clock.current


def test_heartbeat_updates_even_when_kill_switch_blocks_cycle(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    SqliteRiskStateRepository(db_path).save(
        "session-1",
        RiskState(
            day_start_equity=10000.0,
            day_start_date=clock.current.date(),
            peak_equity=10000.0,
            kill_switch_active=True,
            kill_switch_reason="Test",
        ),
    )
    engine, _, _, _ = _build_engine(
        tmp_path, _FixedCandleProvider([]), clock, db_path=db_path
    )
    engine.start()

    engine.run_cycle_once()

    assert engine.session.heartbeat_at == clock.current


# --- CYCLE_ERROR: DataProvider / Strategy / Broker ------------------------------------------


def test_data_provider_error_records_cycle_error_and_keeps_session_running(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    engine, trading_engine, _, _ = _build_engine(
        tmp_path, _FailingProvider(), clock, db_path=db_path
    )
    engine.start()

    result = engine.run_cycle_once()

    assert result is None
    assert trading_engine.status()["running"] is True
    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[-1].event_type == AuditEventType.CYCLE_ERROR
    assert "data_provider" in events[-1].message

    # Session bleibt danach voll funktionsfähig für weitere Zyklen.
    second_result = engine.run_cycle_once()
    assert second_result is None
    assert trading_engine.status()["running"] is True


def test_strategy_error_records_cycle_error(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    t1 = clock.current
    t2 = t1 + timedelta(hours=1)
    provider = _FixedCandleProvider([[_candle(t1, 100.0), _candle(t2, 110.0)]])
    db_path = str(tmp_path / "trading.sqlite3")
    engine, trading_engine, _, _ = _build_engine(
        tmp_path, provider, clock, db_path=db_path, strategy=_FailingStrategy()
    )
    engine.start()

    result = engine.run_cycle_once()

    assert result is None
    assert trading_engine.status()["running"] is True
    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[-1].event_type == AuditEventType.CYCLE_ERROR
    assert "orchestrator" in events[-1].message


def test_broker_error_records_cycle_error(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    t1 = clock.current
    t2 = t1 + timedelta(hours=1)
    provider = _FixedCandleProvider([[_candle(t1, 100.0), _candle(t2, 110.0)]])
    db_path = str(tmp_path / "trading.sqlite3")
    engine, trading_engine, portfolio, _ = _build_engine(
        tmp_path, provider, clock, db_path=db_path, broker=_FailingBroker()
    )
    engine.start()

    result = engine.run_cycle_once()

    assert result is None
    assert trading_engine.status()["running"] is True
    assert portfolio.status().positions == []
    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[-1].event_type == AuditEventType.CYCLE_ERROR
    assert "orchestrator" in events[-1].message


# --- Order History --------------------------------------------------------------------------


def test_successful_execution_is_recorded_in_order_history(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    t1 = clock.current
    t2 = t1 + timedelta(hours=1)
    provider = _FixedCandleProvider([[_candle(t1, 100.0), _candle(t2, 110.0)]])
    db_path = str(tmp_path / "trading.sqlite3")
    engine, _, _, _ = _build_engine(tmp_path, provider, clock, db_path=db_path)
    engine.start()

    engine.run_cycle_once()

    latest = SqliteOrderHistory(db_path).latest("session-1")
    assert latest is not None
    assert latest.symbol == SYMBOL
    assert latest.side == "BUY"
    assert latest.success is True


# --- HealthSnapshot -------------------------------------------------------------------------


def test_health_snapshot_reflects_running_session_after_successful_cycle(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    t1 = clock.current
    t2 = t1 + timedelta(hours=1)
    provider = _FixedCandleProvider([[_candle(t1, 100.0), _candle(t2, 110.0)]])
    engine, _, _, _ = _build_engine(tmp_path, provider, clock)
    engine.start()

    engine.run_cycle_once()
    snapshot = engine.health()

    assert snapshot.session_id == "session-1"
    assert snapshot.engine_running is True
    assert snapshot.heartbeat_at == clock.current
    assert snapshot.last_candle_timestamp == t2
    assert snapshot.last_order is not None
    assert snapshot.last_order.side == "BUY"
    assert snapshot.last_error is None
    assert snapshot.risk_state is not None


def test_health_snapshot_exposes_last_error_after_failure(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    engine, _, _, _ = _build_engine(tmp_path, _FailingProvider(), clock)
    engine.start()

    engine.run_cycle_once()
    snapshot = engine.health()

    assert snapshot.last_error is not None
    assert "data_provider" in snapshot.last_error


# --- Context Manager -------------------------------------------------------------------------


def test_context_manager_starts_and_stops(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    engine, trading_engine, _, _ = _build_engine(
        tmp_path, _FixedCandleProvider([]), clock, db_path=db_path
    )

    with engine:
        assert trading_engine.status()["running"] is True

    assert trading_engine.status()["running"] is False
    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[-1].event_type == AuditEventType.SESSION_STOPPED


def test_context_manager_stops_even_on_exception(tmp_path):

    clock = _Clock(datetime(2026, 7, 18, 12, tzinfo=UTC))
    db_path = str(tmp_path / "trading.sqlite3")
    engine, trading_engine, _, _ = _build_engine(
        tmp_path, _FixedCandleProvider([]), clock, db_path=db_path
    )

    with pytest.raises(ValueError, match="boom"), engine:
        raise ValueError("boom")

    assert trading_engine.status()["running"] is False
    events = SqliteAuditLog(db_path).for_session("session-1")
    assert events[-1].event_type == AuditEventType.SESSION_STOPPED
    assert "Exception" in events[-1].message
