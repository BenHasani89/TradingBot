"""Composition Root: einziger Ort im gesamten Projekt, an dem konkrete
Implementierungen für `DataProvider`, `Strategy`, `Broker` und alle
SQLite-Repositories gewählt und zu einem vollständigen Objektgraphen
zusammengesetzt werden. Kein anderes Modul (auch nicht `cli.commands` oder
`__main__.py`) instanziiert diese konkreten Klassen selbst.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from tradingbot.cli.config import RuntimeConfig, RuntimeMode
from tradingbot.core.engine import TradingEngine
from tradingbot.core.models import ExecutionCostEstimate
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.binance_provider import BinanceDataProvider
from tradingbot.data.market import MarketDataStore
from tradingbot.data.provider import DataProvider
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.execution.broker import Broker, PaperBroker
from tradingbot.execution.live_broker import LiveBroker
from tradingbot.execution.mock_broker import MockLiveBroker, ScenarioProvider
from tradingbot.execution.order_repository import OrderRepository
from tradingbot.execution.persistence import SqliteOrderRepository
from tradingbot.paper_trading.audit import SqliteAuditLog
from tradingbot.paper_trading.engine import PaperTradingEngine
from tradingbot.paper_trading.health import HealthSnapshot, build_health_snapshot
from tradingbot.paper_trading.order_history import SqliteOrderHistory
from tradingbot.paper_trading.persistence import SqliteSessionRepository
from tradingbot.paper_trading.reconciliation import ReconciliationService
from tradingbot.paper_trading.scheduler import SimpleLoopScheduler
from tradingbot.paper_trading.session import SessionMetadata, create_session
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.portfolio.persistence import SqlitePortfolioRepository
from tradingbot.risk.manager import RiskManager
from tradingbot.risk.persistence import SqliteRiskStateRepository
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy
from tradingbot.strategy.simple import SimpleStrategy

LIVE_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_IS_REAL_MONEY"
"""Exakte Zeichenkette, die `build_engine()` für `RuntimeMode.LIVE` als
`live_confirmation` erwartet (statt eines einfachen Booleans) - schwerer
versehentlich zu setzen, keine CLI-/Konfigurationsoption dafür (siehe
`_build_live_broker`)."""

_LIVE_API_KEY_ENV_VAR = "TRADINGBOT_LIVE_API_KEY"
_LIVE_API_SECRET_ENV_VAR = "TRADINGBOT_LIVE_API_SECRET"  # noqa: S105 - Name der ENV-Variable, kein Geheimnis selbst
_LIVE_ENVIRONMENT_ENV_VAR = "TRADINGBOT_LIVE_ENVIRONMENT"

_LIVE_BASE_URLS = {
    "testnet": "https://testnet.binance.vision",
    "production": "https://api.binance.com",
}
"""Binance Spot – erster echter Exchange-Adapter (siehe execution/live_broker.py).
Fehlt `TRADINGBOT_LIVE_ENVIRONMENT` oder hat einen unbekannten Wert, schlägt
`_build_live_broker()` fehl statt still auf einen der beiden Werte
zurückzufallen."""

_STRATEGIES: dict[str, type[Strategy]] = {
    "simple": SimpleStrategy,
    "moving_average": MovingAverageCrossoverStrategy,
}


def _build_strategy(name: str) -> Strategy:
    try:
        strategy_class = _STRATEGIES[name]
    except KeyError:
        raise ValueError(
            f"Unbekannte Strategie: {name!r} (verfügbar: {sorted(_STRATEGIES)})"
        ) from None
    return strategy_class()


def _build_paper_broker(
    config: RuntimeConfig, scenario_provider: ScenarioProvider | None, live_confirmation: str | None
) -> Broker:
    return PaperBroker(fee_percent=config.fee_percent, slippage_percent=config.slippage_percent)


def _build_mock_broker(
    config: RuntimeConfig, scenario_provider: ScenarioProvider | None, live_confirmation: str | None
) -> Broker:
    if scenario_provider is None:
        raise ValueError(
            "RuntimeMode.MOCK erfordert einen scenario_provider - wird ausschliesslich "
            "programmatisch an build_engine() übergeben, es gibt bewusst keine "
            "CLI-/Konfigurationsoption dafür (siehe execution/mock_broker.py)."
        )
    return MockLiveBroker(scenario_provider=scenario_provider)


def _resolve_live_environment() -> str:
    """Liest und validiert `TRADINGBOT_LIVE_ENVIRONMENT` - gemeinsam von
    `_build_live_broker()` und `_build_binance_data_provider()` genutzt,
    damit Handelsausführung und Marktdaten immer dieselbe Binance-Umgebung
    (testnet/production) verwenden. Kein stiller Rückfall auf einen der
    beiden Werte."""

    environment = os.environ.get(_LIVE_ENVIRONMENT_ENV_VAR)
    if environment not in _LIVE_BASE_URLS:
        raise ValueError(
            f"RuntimeMode.LIVE erfordert die Umgebungsvariable {_LIVE_ENVIRONMENT_ENV_VAR!r} "
            f"mit dem Wert 'testnet' oder 'production' - aktueller Wert: {environment!r}. "
            "Kein stiller Rückfall auf einen der beiden Werte."
        )
    return environment


def _build_live_broker(
    config: RuntimeConfig, scenario_provider: ScenarioProvider | None, live_confirmation: str | None
) -> Broker:
    """Baut einen `LiveBroker` - erst nach expliziter Bestätigung und nur
    mit vollständigen Credentials und einer gültigen Umgebung.

    Der zurückgegebene `LiveBroker` führt echte Binance-Spot-Market-Orders
    aus (siehe `execution/live_broker.py`) - diese Factory stellt sicher,
    dass er überhaupt nur mit Bestätigungsphrase *und* vollständigen
    Credentials *und* gültiger `TRADINGBOT_LIVE_ENVIRONMENT` entsteht.
    """

    if live_confirmation != LIVE_CONFIRMATION_PHRASE:
        raise ValueError(
            "RuntimeMode.LIVE erfordert eine explizite Bestätigung - "
            f"live_confirmation muss exakt {LIVE_CONFIRMATION_PHRASE!r} sein. "
            "Keine CLI-/Konfigurationsoption dafür, ausschliesslich programmatisch."
        )

    api_key = os.environ.get(_LIVE_API_KEY_ENV_VAR)
    api_secret = os.environ.get(_LIVE_API_SECRET_ENV_VAR)
    if not api_key or not api_secret:
        raise ValueError(
            f"RuntimeMode.LIVE erfordert die Umgebungsvariablen {_LIVE_API_KEY_ENV_VAR!r} "
            f"und {_LIVE_API_SECRET_ENV_VAR!r} - mindestens eine davon ist nicht gesetzt. "
            "Credentials werden nie in RuntimeConfig/Config-Dateien gespeichert."
        )

    environment = _resolve_live_environment()
    return LiveBroker(api_key=api_key, api_secret=api_secret, base_url=_LIVE_BASE_URLS[environment])


# RuntimeMode.LIVE ist registriert und führt über den zurückgegebenen
# LiveBroker echte Binance-Spot-Market-Orders aus (siehe
# execution/live_broker.py) - deshalb ausschliesslich hinter dem
# vollständigen Sicherheits-Gate aus Bestätigungsphrase, Credential-Prüfung
# und Environment-Prüfung (siehe _build_live_broker). Kein Rückfall auf
# einen anderen Broker, kein stilles Umschalten.
_BROKER_FACTORIES: dict[
    RuntimeMode, Callable[[RuntimeConfig, ScenarioProvider | None, str | None], Broker]
] = {
    RuntimeMode.PAPER: _build_paper_broker,
    RuntimeMode.MOCK: _build_mock_broker,
    RuntimeMode.LIVE: _build_live_broker,
}


def _build_broker(
    config: RuntimeConfig, scenario_provider: ScenarioProvider | None, live_confirmation: str | None
) -> Broker:
    try:
        factory = _BROKER_FACTORIES[config.mode]
    except KeyError:
        raise ValueError(
            f"RuntimeMode {config.mode.value!r} ist architektonisch vorbereitet, aber "
            "noch kein Broker dafür registriert."
        ) from None
    return factory(config, scenario_provider, live_confirmation)


def _build_simulated_data_provider(config: RuntimeConfig) -> DataProvider:
    return SimulatedDataProvider()


def _build_binance_data_provider(config: RuntimeConfig) -> DataProvider:
    """Baut einen `BinanceDataProvider` - dieselbe Umgebungsauflösung wie
    `_build_live_broker()`, damit Marktdaten und Order-Ausführung immer
    gegen dieselbe Binance-Umgebung laufen (siehe
    `data/binance_provider.py`-Moduldocstring). Braucht keine Credentials,
    keine eigene Bestätigungsphrase - der öffentliche `klines`-Endpoint
    ist unsigniert."""

    environment = _resolve_live_environment()
    return BinanceDataProvider(base_url=_LIVE_BASE_URLS[environment])


# RuntimeMode.LIVE erhält echte Binance-Marktdaten statt SimulatedDataProvider
# - PAPER/MOCK bleiben unverändert bei SimulatedDataProvider (siehe
# data/binance_provider.py). Dieselbe Dict-Dispatch-Struktur wie
# _BROKER_FACTORIES, kein if/else im Trading-Code.
_DATA_PROVIDER_FACTORIES: dict[RuntimeMode, Callable[[RuntimeConfig], DataProvider]] = {
    RuntimeMode.PAPER: _build_simulated_data_provider,
    RuntimeMode.MOCK: _build_simulated_data_provider,
    RuntimeMode.LIVE: _build_binance_data_provider,
}


def _build_data_provider(config: RuntimeConfig) -> DataProvider:
    try:
        factory = _DATA_PROVIDER_FACTORIES[config.mode]
    except KeyError:
        raise ValueError(
            f"RuntimeMode {config.mode.value!r} ist architektonisch vorbereitet, aber "
            "noch kein DataProvider dafür registriert."
        ) from None
    return factory(config)


def build_engine(
    config: RuntimeConfig,
    scenario_provider: ScenarioProvider | None = None,
    live_confirmation: str | None = None,
) -> tuple[PaperTradingEngine, SimpleLoopScheduler]:
    """Baut den vollständigen Objektgraphen für eine neue Paper-Trading-Session.

    `scenario_provider` ist ausschliesslich für `RuntimeMode.MOCK` relevant
    (siehe `_build_mock_broker`), `live_confirmation` ausschliesslich für
    `RuntimeMode.LIVE` (siehe `_build_live_broker`, `LIVE_CONFIRMATION_PHRASE`).
    Beide werden nie aus `config` abgeleitet - reine Python-Übergabe, keine
    CLI-Konfiguration.
    """

    trading_engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=config.initial_capital)
    broker = _build_broker(config, scenario_provider, live_confirmation)
    order_repository: OrderRepository = SqliteOrderRepository(config.db_path)
    orchestrator = TradingOrchestrator(
        engine=trading_engine,
        strategy=_build_strategy(config.strategy_name),
        risk_manager=RiskManager(max_position_size=config.max_position_size),
        portfolio=portfolio,
        broker=broker,
        # Unabhängig vom gewählten Broker aus denselben Werten wie oben -
        # TradingOrchestrator liest Fee/Slippage nicht mehr vom Broker selbst
        # (siehe core/orchestrator.py, core/models.py::ExecutionCostEstimate).
        cost_estimate=ExecutionCostEstimate(
            fee_percent=config.fee_percent, slippage_percent=config.slippage_percent
        ),
        # Persistente Order-Historie für die Paper-Trading-Laufzeit (überlebt
        # einen Neustart) - im Unterschied zum Backtest-Pfad, der denselben
        # `TradingOrchestrator` ohne `order_repository` verwendet und dadurch
        # automatisch beim In-Memory-Standard bleibt (siehe
        # `core/orchestrator.py`).
        order_repository=order_repository,
    )

    session = create_session(
        symbol=config.symbol, timeframe=config.timeframe, strategy_name=config.strategy_name
    )
    if config.session_id is not None:
        session.session_id = config.session_id

    # Derselbe broker/order_repository wie oben - Reconciliation muss gegen
    # denselben Zustand prüfen, den TradingOrchestrator tatsächlich verwendet
    # (siehe paper_trading/reconciliation.py).
    reconciliation_service = ReconciliationService(
        broker=broker, order_repository=order_repository
    )

    engine = PaperTradingEngine(
        engine=trading_engine,
        provider=_build_data_provider(config),
        store=MarketDataStore(),
        orchestrator=orchestrator,
        portfolio=portfolio,
        portfolio_repository=SqlitePortfolioRepository(config.db_path),
        risk_repository=SqliteRiskStateRepository(config.db_path),
        session=session,
        session_repository=SqliteSessionRepository(config.db_path),
        audit_log=SqliteAuditLog(config.db_path),
        order_history=SqliteOrderHistory(config.db_path),
        symbol=config.symbol,
        timeframe=config.timeframe,
        candle_limit=config.candle_limit,
        max_daily_loss_percent=config.max_daily_loss_percent,
        max_drawdown_percent=config.max_drawdown_percent,
        max_exposure_percent=config.max_exposure_percent,
        max_exposure_per_asset_percent=config.max_exposure_per_asset_percent,
        reconciliation_service=reconciliation_service,
    )

    return engine, SimpleLoopScheduler()


def load_session(config: RuntimeConfig, session_id: str) -> SessionMetadata | None:
    """Lädt eine einzelne Session, unabhängig von einem laufenden `start`-Prozess."""

    return SqliteSessionRepository(config.db_path).load(session_id)


def load_all_sessions(config: RuntimeConfig) -> list[SessionMetadata]:
    """Lädt alle bekannten Sessions."""

    return SqliteSessionRepository(config.db_path).all()


def load_health_snapshot(config: RuntimeConfig, session_id: str) -> HealthSnapshot | None:
    """Baut einen `HealthSnapshot` für eine bestehende Session aus einem
    separaten Prozess heraus. `engine_running` ist dabei immer `False` und
    `last_candle_timestamp` immer `None` - beides ist nur innerhalb des
    laufenden `start`-Prozesses bekannt (kein prozessübergreifender
    Laufzeit-Zustand, keine Candle-Persistenz - bewusste Entscheidung dieser
    Phase). `risk_id` folgt derselben Default-Konvention wie
    `PaperTradingEngine` (identisch zu `session_id`).
    """

    session = SqliteSessionRepository(config.db_path).load(session_id)
    if session is None:
        return None

    risk_state = SqliteRiskStateRepository(config.db_path).load(session_id)
    order_history = SqliteOrderHistory(config.db_path)

    return build_health_snapshot(
        session=session,
        trading_engine=TradingEngine(),
        store=MarketDataStore(),
        symbol=session.symbol,
        order_history=order_history,
        risk_state=risk_state,
        last_error=None,
    )
