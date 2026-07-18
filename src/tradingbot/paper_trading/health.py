"""Health-Snapshot: aggregiert bestehende Zustände zu einem konsistenten
Überblick - keine eigene Persistenz, keine neue Wahrheitsquelle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tradingbot.core.engine import TradingEngine
from tradingbot.data.market import MarketDataStore
from tradingbot.paper_trading.order_history import OrderExecution, SqliteOrderHistory
from tradingbot.paper_trading.session import SessionMetadata
from tradingbot.risk.risk_state import RiskState


@dataclass
class HealthSnapshot:
    """Momentaufnahme des Betriebszustands einer Paper-Trading-Session."""

    session_id: str
    engine_running: bool
    heartbeat_at: datetime | None
    last_candle_timestamp: datetime | None
    last_order: OrderExecution | None
    last_error: str | None
    risk_state: RiskState | None


def build_health_snapshot(
    session: SessionMetadata,
    trading_engine: TradingEngine,
    store: MarketDataStore,
    symbol: str,
    order_history: SqliteOrderHistory,
    risk_state: RiskState | None,
    last_error: str | None,
) -> HealthSnapshot:
    """Baut einen `HealthSnapshot` ausschliesslich aus bereits vorhandenen
    Quellen zusammen (`TradingEngine`, `MarketDataStore`, `SqliteOrderHistory`,
    `SessionMetadata`, `RiskState`) - liest nur, schreibt nichts."""

    last_candles = store.latest(symbol, 1)
    last_candle_timestamp = last_candles[-1].timestamp if last_candles else None

    return HealthSnapshot(
        session_id=session.session_id,
        engine_running=trading_engine.status()["running"],
        heartbeat_at=session.heartbeat_at,
        last_candle_timestamp=last_candle_timestamp,
        last_order=order_history.latest(session.session_id),
        last_error=last_error,
        risk_state=risk_state,
    )
