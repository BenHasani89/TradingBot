import httpx
import pytest

import tradingbot.execution.live_broker as live_broker_module
from tradingbot.cli import composition
from tradingbot.cli.config import RuntimeMode, build_config
from tradingbot.execution.broker import PaperBroker
from tradingbot.execution.live_broker import LiveBroker
from tradingbot.execution.mock_broker import MockExecutionScenario, MockLiveBroker, MockOutcome
from tradingbot.execution.models import OrderStatus
from tradingbot.execution.persistence import SqliteOrderRepository
from tradingbot.paper_trading.engine import PaperTradingEngine
from tradingbot.paper_trading.scheduler import Scheduler


def _config(tmp_path, **overrides):

    return build_config(db_path=str(tmp_path / "trading.sqlite3"), **overrides)


def test_build_engine_wires_symbol_and_timeframe(tmp_path):

    config = _config(tmp_path, symbol="ETHUSDT", timeframe="4h")

    engine, scheduler = composition.build_engine(config)

    assert isinstance(engine, PaperTradingEngine)
    assert isinstance(scheduler, Scheduler)
    assert engine.session.symbol == "ETHUSDT"
    assert engine.session.timeframe == "4h"


def test_build_engine_respects_explicit_session_id(tmp_path):

    config = _config(tmp_path, session_id="custom-session")

    engine, _ = composition.build_engine(config)

    assert engine.session.session_id == "custom-session"


def test_build_engine_generates_session_id_when_not_given(tmp_path):

    config = _config(tmp_path)

    engine, _ = composition.build_engine(config)

    assert len(engine.session.session_id) == 36  # UUID4-Format


def test_build_engine_unknown_strategy_raises(tmp_path):

    config = _config(tmp_path, strategy_name="does-not-exist")

    with pytest.raises(ValueError, match="Unbekannte Strategie"):
        composition.build_engine(config)


def test_build_engine_start_and_stop_persists_session(tmp_path):

    config = _config(tmp_path, session_id="session-1")
    engine, _ = composition.build_engine(config)

    engine.start()
    engine.stop()

    session = composition.load_session(config, "session-1")
    assert session is not None
    assert session.status == "stopped"


def test_load_session_returns_none_for_unknown_id(tmp_path):

    config = _config(tmp_path)

    assert composition.load_session(config, "unknown") is None


def test_load_all_sessions_returns_saved_sessions(tmp_path):

    config = _config(tmp_path, session_id="session-1")
    engine, _ = composition.build_engine(config)
    engine.start()
    engine.stop()

    all_sessions = composition.load_all_sessions(config)

    assert [s.session_id for s in all_sessions] == ["session-1"]


def test_load_health_snapshot_returns_none_for_unknown_session(tmp_path):

    config = _config(tmp_path)

    assert composition.load_health_snapshot(config, "unknown") is None


def test_load_health_snapshot_reflects_persisted_state_from_separate_process(tmp_path):

    config = _config(tmp_path, session_id="session-1", candle_limit=5)
    engine, _ = composition.build_engine(config)
    engine.start()
    engine.run_cycle_once()
    engine.stop()

    snapshot = composition.load_health_snapshot(config, "session-1")

    assert snapshot is not None
    assert snapshot.session_id == "session-1"
    # Separater Prozessaufruf: Engine nie gestartet, keine Candle-Persistenz.
    assert snapshot.engine_running is False
    assert snapshot.last_candle_timestamp is None
    assert snapshot.risk_state is not None


# --- Option B: PaperTrading-Pfad verwendet persistentes OrderRepository -----------------------


def test_paper_trading_path_persists_orders_in_sqlite_order_repository(tmp_path):
    """Der vollständige PaperTradingEngine-Pfad (über build_engine ->
    TradingOrchestrator) muss ohne jede eigene Codeänderung an
    PaperTradingEngine ein SqliteOrderRepository befüllen, sobald
    composition.py eines injiziert."""

    config = _config(tmp_path, session_id="session-1", candle_limit=5)
    engine, _ = composition.build_engine(config)
    engine.start()

    engine.run_cycle_once()
    engine.stop()

    order_repository = SqliteOrderRepository(config.db_path)
    records = order_repository.all()

    assert len(records) >= 1
    assert records[0].status == OrderStatus.FILLED
    assert records[0].execution_result is not None
    assert records[0].execution_result.success is True


# --- RuntimeMode / Broker-Dispatch -----------------------------------------------------------


def test_build_engine_default_mode_uses_paper_broker(tmp_path):

    config = _config(tmp_path)
    engine, _ = composition.build_engine(config)

    assert isinstance(engine._orchestrator._broker, PaperBroker)


def test_build_engine_mock_mode_without_scenario_provider_raises(tmp_path):

    config = _config(tmp_path, mode=RuntimeMode.MOCK)

    with pytest.raises(ValueError, match="scenario_provider"):
        composition.build_engine(config)


def test_build_engine_mock_mode_with_scenario_provider_uses_mock_broker(tmp_path):

    config = _config(tmp_path, mode=RuntimeMode.MOCK)

    def scenario_provider(order):
        return MockExecutionScenario(MockOutcome.SUCCESS)

    engine, _ = composition.build_engine(config, scenario_provider=scenario_provider)

    assert isinstance(engine._orchestrator._broker, MockLiveBroker)


def test_build_engine_mock_mode_executes_trade_via_scenario(tmp_path):

    config = _config(tmp_path, session_id="session-1", candle_limit=5, mode=RuntimeMode.MOCK)

    def scenario_provider(order):
        return MockExecutionScenario(MockOutcome.SUCCESS)

    engine, _ = composition.build_engine(config, scenario_provider=scenario_provider)
    engine.start()

    result = engine.run_cycle_once()
    engine.stop()

    assert result is not None
    assert result.execution is not None
    assert result.execution.success is True


def test_build_engine_live_mode_without_confirmation_raises(tmp_path, monkeypatch):

    monkeypatch.setenv("TRADINGBOT_LIVE_API_KEY", "key")
    monkeypatch.setenv("TRADINGBOT_LIVE_API_SECRET", "secret")
    config = _config(tmp_path, mode=RuntimeMode.LIVE)

    with pytest.raises(ValueError, match="Bestätigung"):
        composition.build_engine(config)


def test_build_engine_live_mode_with_wrong_confirmation_raises(tmp_path, monkeypatch):

    monkeypatch.setenv("TRADINGBOT_LIVE_API_KEY", "key")
    monkeypatch.setenv("TRADINGBOT_LIVE_API_SECRET", "secret")
    config = _config(tmp_path, mode=RuntimeMode.LIVE)

    with pytest.raises(ValueError, match="Bestätigung"):
        composition.build_engine(config, live_confirmation="yes please")


def test_build_engine_live_mode_confirmed_but_missing_credentials_raises(tmp_path, monkeypatch):

    monkeypatch.delenv("TRADINGBOT_LIVE_API_KEY", raising=False)
    monkeypatch.delenv("TRADINGBOT_LIVE_API_SECRET", raising=False)
    config = _config(tmp_path, mode=RuntimeMode.LIVE)

    with pytest.raises(ValueError, match="TRADINGBOT_LIVE_API_KEY"):
        composition.build_engine(
            config, live_confirmation=composition.LIVE_CONFIRMATION_PHRASE
        )


def test_build_engine_live_mode_confirmed_with_credentials_but_missing_environment_raises(
    tmp_path, monkeypatch
):

    monkeypatch.setenv("TRADINGBOT_LIVE_API_KEY", "key")
    monkeypatch.setenv("TRADINGBOT_LIVE_API_SECRET", "secret")
    monkeypatch.delenv("TRADINGBOT_LIVE_ENVIRONMENT", raising=False)
    config = _config(tmp_path, mode=RuntimeMode.LIVE)

    with pytest.raises(ValueError, match="TRADINGBOT_LIVE_ENVIRONMENT"):
        composition.build_engine(
            config, live_confirmation=composition.LIVE_CONFIRMATION_PHRASE
        )


def _patch_binance_http(monkeypatch, handler) -> None:
    """Ersetzt die von `LiveBroker` intern konstruierte `httpx.Client`-
    Instanz durch eine, die über `httpx.MockTransport` läuft - kein echter
    Netzwerkzugriff in der Testsuite, auch nicht für den Zeit-Sync beim
    Konstruktor.

    `live_broker_module.httpx` ist dasselbe Modulobjekt wie das hier
    importierte `httpx` - der echte `httpx.Client` wird deshalb vor dem
    Patchen separat gesichert, sonst würde `_fake_client` sich selbst
    rekursiv aufrufen."""

    real_client_class = httpx.Client

    def _fake_client(**kwargs):
        return real_client_class(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(live_broker_module.httpx, "Client", _fake_client)


def _time_only_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/v3/time"
    return httpx.Response(200, json={"serverTime": 1700000000000})


def test_build_engine_live_mode_confirmed_with_credentials_builds_live_broker(
    tmp_path, monkeypatch
):

    monkeypatch.setenv("TRADINGBOT_LIVE_API_KEY", "key")
    monkeypatch.setenv("TRADINGBOT_LIVE_API_SECRET", "secret")
    monkeypatch.setenv("TRADINGBOT_LIVE_ENVIRONMENT", "testnet")
    _patch_binance_http(monkeypatch, _time_only_handler)
    config = _config(tmp_path, mode=RuntimeMode.LIVE)

    engine, _ = composition.build_engine(
        config, live_confirmation=composition.LIVE_CONFIRMATION_PHRASE
    )

    assert isinstance(engine._orchestrator._broker, LiveBroker)


def test_build_engine_live_mode_executes_trade_via_mocked_binance(tmp_path, monkeypatch):
    """Volles Zusammenspiel gegen eine simulierte Binance-Antwort - kein
    echter Netzwerkzugriff, aber derselbe Codepfad wie im echten Betrieb."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1700000000000})
        if request.url.path == "/api/v3/order":
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "orderId": 1,
                    "clientOrderId": "test",
                    "status": "FILLED",
                    "executedQty": "0.01",
                    "cummulativeQuoteQty": "500.0",
                    "fills": [
                        {"price": "50000.0", "qty": "0.01", "commission": "0.5"}
                    ],
                },
            )
        raise AssertionError(f"Unerwarteter Aufruf: {request.url.path}")

    monkeypatch.setenv("TRADINGBOT_LIVE_API_KEY", "key")
    monkeypatch.setenv("TRADINGBOT_LIVE_API_SECRET", "secret")
    monkeypatch.setenv("TRADINGBOT_LIVE_ENVIRONMENT", "testnet")
    _patch_binance_http(monkeypatch, handler)
    config = _config(
        tmp_path, session_id="session-1", candle_limit=5, mode=RuntimeMode.LIVE
    )

    engine, _ = composition.build_engine(
        config, live_confirmation=composition.LIVE_CONFIRMATION_PHRASE
    )
    engine.start()

    result = engine.run_cycle_once()

    assert result is not None
    assert result.execution is not None
    assert result.execution.success is True


def test_build_engine_paper_mode_ignores_scenario_provider(tmp_path):
    """`scenario_provider` ist nur für MOCK relevant - PAPER darf ihn
    ignorieren, statt einen Fehler zu werfen."""

    config = _config(tmp_path)

    def scenario_provider(order):
        raise AssertionError("darf für PAPER nie aufgerufen werden")

    engine, _ = composition.build_engine(config, scenario_provider=scenario_provider)

    assert isinstance(engine._orchestrator._broker, PaperBroker)
