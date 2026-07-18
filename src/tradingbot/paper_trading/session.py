"""Session-Metadaten einer Paper-Trading-Laufzeitumgebung."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

SessionStatus = Literal["running", "stopped"]


@dataclass
class SessionMetadata:
    """Beschreibt eine einzelne Paper-Trading-Session.

    Rein deskriptiv (Konfiguration + Lebenszyklus-Status) - kennt weder
    Portfolio- noch Risk-State. Die Zuordnung von `session_id` zu
    `portfolio_id`/`risk_id` ist Aufgabe von
    `paper_trading.engine.PaperTradingEngine`, nicht dieser Klasse.

    `heartbeat_at` wird bei jedem verarbeiteten `run_cycle_once()`-Aufruf
    aktualisiert und dient der Erkennung abgestürzter Sessions: bleibt
    `status` dauerhaft `"running"`, obwohl `heartbeat_at` seit langem nicht
    mehr aktualisiert wurde, deutet das auf einen unsauberen
    Prozess-Abbruch hin statt auf eine sauber laufende Session.
    """

    session_id: str
    symbol: str
    timeframe: str
    strategy_name: str
    started_at: datetime
    stopped_at: datetime | None = None
    status: SessionStatus = "running"
    heartbeat_at: datetime | None = None


def create_session(
    symbol: str,
    timeframe: str,
    strategy_name: str,
    now: datetime | None = None,
) -> SessionMetadata:
    """Erstellt eine neue `SessionMetadata` mit automatischer `session_id`
    (UUID4, analog zu `research_tracking.models.ExperimentMetadata`)."""

    return SessionMetadata(
        session_id=str(uuid4()),
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
        started_at=now if now is not None else datetime.now(UTC),
    )
