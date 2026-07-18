"""CLI-Kommandos: reine Ablauf- und Formatierungslogik - keine Objekt-
Konstruktion (siehe `tradingbot.cli.composition`, dem einzigen Ort dafür).

`format_*`-Funktionen sind reine Funktionen (Daten rein, Text+Exit-Code
raus) und dadurch ohne echte Dateien/Prozesse testbar. `run_start()` nimmt
einen bereits fertig gebauten `PaperTradingEngine`/`Scheduler` entgegen,
nicht die `RuntimeConfig` selbst - dadurch in Tests mit Fake-Abhängigkeiten
(wie in `test_paper_trading_engine.py`) genauso ansteuerbar wie die Engine
selbst.
"""

from __future__ import annotations

import signal

from tradingbot.paper_trading.engine import PaperTradingEngine
from tradingbot.paper_trading.health import HealthSnapshot
from tradingbot.paper_trading.scheduler import Scheduler
from tradingbot.paper_trading.session import SessionMetadata


def run_start(engine: PaperTradingEngine, scheduler: Scheduler, interval_seconds: float) -> int:
    """Führt die blockierende Trading-Session aus, bis `scheduler.stop()`
    aufgerufen wird (regulär über SIGINT/SIGTERM, siehe
    `_register_shutdown_handlers`). Der Context-Manager auf `engine`
    garantiert, dass `engine.stop()` in jedem Fall läuft - auch bei einer
    Exception innerhalb der Schleife.
    """

    _register_shutdown_handlers(scheduler)

    with engine:
        scheduler.run(engine.run_cycle_once, interval_seconds=interval_seconds)

    return 0


def _register_shutdown_handlers(scheduler: Scheduler) -> None:
    """Registriert SIGINT/SIGTERM, um die Schleife sauber zu beenden - kein
    Daemon-/PID-Konzept, kein eigenes `stop`-Kommando (siehe
    Architekturentscheidung: der Bot läuft als Foreground-Prozess)."""

    def _handle_signal(signum: int, frame: object) -> None:
        scheduler.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def format_status(session: SessionMetadata | None, session_id: str) -> tuple[str, int]:
    """Formatiert die Ausgabe von `status`. Gibt `(text, exit_code)` zurück."""

    if session is None:
        return f"Keine Session gefunden: {session_id}", 1

    lines = [
        f"session_id:   {session.session_id}",
        f"symbol:       {session.symbol} ({session.timeframe})",
        f"status:       {session.status}",
        f"started_at:   {session.started_at}",
        f"stopped_at:   {session.stopped_at}",
        f"heartbeat_at: {session.heartbeat_at}",
    ]
    return "\n".join(lines), 0


def format_health(snapshot: HealthSnapshot | None, session_id: str) -> tuple[str, int]:
    """Formatiert die Ausgabe von `health`. Gibt `(text, exit_code)` zurück.

    `engine_running` ist bei separatem Prozessaufruf immer `False`,
    `last_candle_timestamp` immer `None` (siehe
    `composition.load_health_snapshot`).
    """

    if snapshot is None:
        return f"Keine Session gefunden: {session_id}", 1

    lines = [
        f"session_id:            {snapshot.session_id}",
        f"engine_running:        {snapshot.engine_running} (separater Prozess: immer False)",
        f"heartbeat_at:          {snapshot.heartbeat_at}",
        f"last_candle_timestamp: {snapshot.last_candle_timestamp} "
        "(keine Candle-Persistenz: immer None)",
        f"last_order:            {snapshot.last_order}",
        f"last_error:            {snapshot.last_error}",
        f"risk_state:            {snapshot.risk_state}",
    ]
    return "\n".join(lines), 0


def format_sessions(all_sessions: list[SessionMetadata]) -> tuple[str, int]:
    """Formatiert die Ausgabe von `sessions`. Gibt `(text, exit_code)` zurück."""

    if not all_sessions:
        return "Keine Sessions gefunden.", 0

    lines = [
        f"{session.session_id}  {session.symbol}  {session.status}  "
        f"heartbeat={session.heartbeat_at}"
        for session in all_sessions
    ]
    return "\n".join(lines), 0
