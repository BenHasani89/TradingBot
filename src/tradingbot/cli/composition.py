"""Composition Root: einziger Ort im gesamten Projekt, an dem konkrete
Implementierungen für `DataProvider`, `Strategy`, `Broker` und alle
SQLite-Repositories gewählt und zu einem vollständigen Objektgraphen
zusammengesetzt werden. Kein anderes Modul (auch nicht `cli.commands` oder
`__main__.py`) instanziiert diese konkreten Klassen selbst.
"""

from __future__ import annotations

from tradingbot.cli.config import RuntimeConfig
from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.market import MarketDataStore
from tradingbot.data.simulated_provider import SimulatedDataProvider
from tradingbot.execution.broker import PaperBroker
from tradingbot.execution.persistence import SqliteOrderRepository
from tradingbot.paper_trading.audit import SqliteAuditLog
from tradingbot.paper_trading.engine import PaperTradingEngine
from tradingbot.paper_trading.health import HealthSnapshot, build_health_snapshot
from tradingbot.paper_trading.order_history import SqliteOrderHistory
from tradingbot.paper_trading.persistence import SqliteSessionRepository
from tradingbot.paper_trading.scheduler import SimpleLoopScheduler
from tradingbot.paper_trading.session import SessionMetadata, create_session
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.portfolio.persistence import SqlitePortfolioRepository
from tradingbot.risk.manager import RiskManager
from tradingbot.risk.persistence import SqliteRiskStateRepository
from tradingbot.strategy.base import Strategy
from tradingbot.strategy.moving_average import MovingAverageCrossoverStrategy
from tradingbot.strategy.simple import SimpleStrategy

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


def build_engine(config: RuntimeConfig) -> tuple[PaperTradingEngine, SimpleLoopScheduler]:
    """Baut den vollständigen Objektgraphen für eine neue Paper-Trading-Session."""

    trading_engine = TradingEngine()
    portfolio = PortfolioManager(initial_capital=config.initial_capital)
    orchestrator = TradingOrchestrator(
        engine=trading_engine,
        strategy=_build_strategy(config.strategy_name),
        risk_manager=RiskManager(max_position_size=config.max_position_size),
        portfolio=portfolio,
        broker=PaperBroker(
            fee_percent=config.fee_percent, slippage_percent=config.slippage_percent
        ),
        # Persistente Order-Historie für die Paper-Trading-Laufzeit (überlebt
        # einen Neustart) - im Unterschied zum Backtest-Pfad, der denselben
        # `TradingOrchestrator` ohne `order_repository` verwendet und dadurch
        # automatisch beim In-Memory-Standard bleibt (siehe
        # `core/orchestrator.py`).
        order_repository=SqliteOrderRepository(config.db_path),
    )

    session = create_session(
        symbol=config.symbol, timeframe=config.timeframe, strategy_name=config.strategy_name
    )
    if config.session_id is not None:
        session.session_id = config.session_id

    engine = PaperTradingEngine(
        engine=trading_engine,
        provider=SimulatedDataProvider(),
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
