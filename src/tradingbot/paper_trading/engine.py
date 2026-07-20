"""Paper-Trading-Laufzeitumgebung: verbindet Datenabruf, Sicherheitsprüfung,
`TradingOrchestrator` und Persistenz zu einer dauerhaft betreibbaren Session.

`TradingOrchestrator` bleibt dabei unverändert der atomare Einzelzyklus
(Strategie -> RiskManager -> Cash-Check -> Broker -> Portfolio-Buchung) -
diese Schicht entscheidet nur, *ob* und *wann* er aufgerufen wird, und
kümmert sich um alles, was über einen einzelnen Zyklus hinausgeht (Zustand
laden/speichern, Sicherheitslimits, Audit-Protokoll, Fehlerbehandlung).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType

from loguru import logger

from tradingbot.core.engine import TradingEngine
from tradingbot.core.models import TradingCycleResult
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.market import MarketDataStore
from tradingbot.data.provider import DataProvider
from tradingbot.paper_trading.audit import AuditEventType, SqliteAuditLog
from tradingbot.paper_trading.health import HealthSnapshot, build_health_snapshot
from tradingbot.paper_trading.order_history import OrderExecution, SqliteOrderHistory
from tradingbot.paper_trading.reconciliation import ReconciliationResult, ReconciliationService
from tradingbot.paper_trading.repository import SessionRepository
from tradingbot.paper_trading.session import SessionMetadata
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.portfolio.repository import PortfolioRepository
from tradingbot.risk.repository import RiskStateRepository
from tradingbot.risk.risk_state import RiskState
from tradingbot.risk.runtime_limits import PortfolioRiskGuard


class PaperTradingEngine:
    """Führt eine dauerhafte Paper-Trading-Session aus.

    Baut den `PortfolioRiskGuard` selbst in `start()` auf (statt ihn fertig
    entgegenzunehmen), da geladener `RiskState` in ein bestehendes
    `PortfolioRiskGuard`-Objekt nicht ohne Zugriff auf dessen interne
    Attribute eingespielt werden könnte - `PortfolioRiskGuard` bleibt dafür
    unverändert.

    `run_cycle_once()` fängt Fehler aus jeder externen Abhängigkeit
    (Datenabruf, Risk-Guard/Persistenz, Orchestrator inkl. Strategie und
    Broker, Order-Historie/Portfolio-Persistenz) phasenweise ab: ein
    einzelner Fehler protokolliert ein `CYCLE_ERROR`-Audit-Event und bricht
    nur den aktuellen Zyklus ab - die Session läuft weiter, kein
    automatischer Stop. Schlägt sogar das Audit-Log selbst fehl, wird der
    Fehler zusätzlich über `loguru` protokolliert, damit er nicht spurlos
    verschwindet.

    `portfolio_id`/`risk_id` sind von `session_id` unabhängige Schlüssel
    (defaulten auf `session.session_id`) - die Zuordnung kennt ausschliesslich
    diese Klasse, `PortfolioRepository`/`RiskStateRepository` bleiben
    dadurch von Session-Konzepten unberührt.
    """

    def __init__(
        self,
        engine: TradingEngine,
        provider: DataProvider,
        store: MarketDataStore,
        orchestrator: TradingOrchestrator,
        portfolio: PortfolioManager,
        portfolio_repository: PortfolioRepository,
        risk_repository: RiskStateRepository,
        session: SessionMetadata,
        session_repository: SessionRepository,
        audit_log: SqliteAuditLog,
        order_history: SqliteOrderHistory,
        symbol: str,
        timeframe: str,
        candle_limit: int,
        max_daily_loss_percent: float,
        max_drawdown_percent: float,
        max_exposure_percent: float,
        max_exposure_per_asset_percent: float,
        portfolio_id: str | None = None,
        risk_id: str | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        reconciliation_service: ReconciliationService | None = None,
    ) -> None:
        self._engine = engine
        self._provider = provider
        self._store = store
        self._orchestrator = orchestrator
        self._portfolio = portfolio
        self._portfolio_repository = portfolio_repository
        self._risk_repository = risk_repository
        self._session = session
        self._session_repository = session_repository
        self._audit_log = audit_log
        self._order_history = order_history
        self._reconciliation_service = reconciliation_service
        self._symbol = symbol
        self._timeframe = timeframe
        self._candle_limit = candle_limit
        self._max_daily_loss_percent = max_daily_loss_percent
        self._max_drawdown_percent = max_drawdown_percent
        self._max_exposure_percent = max_exposure_percent
        self._max_exposure_per_asset_percent = max_exposure_per_asset_percent
        self._portfolio_id = portfolio_id if portfolio_id is not None else session.session_id
        self._risk_id = risk_id if risk_id is not None else session.session_id
        self._now = now
        self._risk_guard: PortfolioRiskGuard | None = None
        self._last_error: str | None = None

    @property
    def session(self) -> SessionMetadata:
        return self._session

    @property
    def risk_guard(self) -> PortfolioRiskGuard | None:
        """`None`, bis `start()` aufgerufen wurde."""

        return self._risk_guard

    def __enter__(self) -> PaperTradingEngine:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Garantiert `stop()` beim Verlassen des `with`-Blocks - auch bei
        einer Exception im Block. Die Exception wird nicht unterdrückt
        (kein `return True`), nur `stop()` wird vorher sichergestellt."""

        reason = (
            "Regulärer Shutdown" if exc_type is None else f"Shutdown durch Exception: {exc_value}"
        )
        self.stop(reason=reason)

    def start(self) -> None:
        """Lädt Portfolio- und Risk-State (falls vorhanden), baut den
        `PortfolioRiskGuard` auf und startet die zugrunde liegende
        `TradingEngine`.

        Ist ein `reconciliation_service` konfiguriert, wird davor
        `reconcile_pending()` geprüft. Bei jedem erkannten Mismatch: der
        Kill-Switch wird aktiviert und der resultierende `RiskState` sofort
        persistiert (er darf einen Neustart nicht ungespeichert überstehen
        - nur diese eine Aktion, keine automatische Portfolio-Korrektur,
        kein Replay), ein `RECONCILIATION_MISMATCH`-Audit-Event wird
        geschrieben, und `start()` bricht mit `RuntimeError` ab, *bevor*
        `TradingEngine.start()` aufgerufen wird - kein Zyklus kann in einer
        Session mit unaufgeklärter Order-Diskrepanz laufen. Auflösung
        erfordert manuellen Eingriff (`PortfolioRiskGuard.
        reset_kill_switch()`), kein automatischer Mechanismus dafür.

        Raises:
            RuntimeError: bei mindestens einem Reconciliation-Mismatch.
        """

        portfolio_state = self._portfolio_repository.load(self._portfolio_id)
        if portfolio_state is not None:
            self._portfolio.restore_state(portfolio_state)

        risk_state = self._risk_repository.load(self._risk_id)
        if risk_state is None:
            current_capital = self._portfolio.export_state().capital
            risk_state = RiskState(
                day_start_equity=current_capital,
                day_start_date=self._now().date(),
                peak_equity=current_capital,
            )

        self._risk_guard = PortfolioRiskGuard(
            state=risk_state,
            max_daily_loss_percent=self._max_daily_loss_percent,
            max_drawdown_percent=self._max_drawdown_percent,
            max_exposure_percent=self._max_exposure_percent,
            max_exposure_per_asset_percent=self._max_exposure_per_asset_percent,
            now=self._now,
        )

        if self._reconciliation_service is not None:
            mismatches = self._run_startup_reconciliation()
            if mismatches:
                raise RuntimeError(
                    f"Session-Start abgebrochen: {len(mismatches)} Reconciliation-"
                    f"Mismatch(es) erkannt (Session {self._session.session_id}). "
                    "Kill-Switch aktiv und persistiert - manueller Eingriff "
                    "erforderlich (siehe Audit-Log, PortfolioRiskGuard.reset_kill_switch())."
                )

        self._session_repository.save(self._session)
        self._engine.start()
        self._audit_log.record(
            self._session.session_id,
            AuditEventType.SESSION_STARTED,
            f"Session gestartet: {self._symbol} {self._timeframe}",
            now=self._now(),
        )
        logger.info("Paper-Trading-Session gestartet: {}", self._session.session_id)

    def _run_startup_reconciliation(self) -> list[ReconciliationResult]:
        """Vergleicht offene Orders mit dem Broker, eskaliert jeden
        Mismatch (Kill-Switch + Audit-Event) und gibt die gefundenen
        Mismatches zurück - leer, wenn alles übereinstimmt."""

        results = self._reconciliation_service.reconcile_pending()
        mismatches = [result for result in results if not result.matched]

        for mismatch in mismatches:
            self._risk_guard.trigger_kill_switch(
                f"Reconciliation-Mismatch bei Order {mismatch.client_order_id}: "
                f"{mismatch.reason}"
            )
            self._audit_log.record(
                self._session.session_id,
                AuditEventType.RECONCILIATION_MISMATCH,
                (
                    f"{mismatch.client_order_id}: lokal="
                    f"{mismatch.local_status.value if mismatch.local_status else None}, "
                    f"broker={mismatch.broker_status.value if mismatch.broker_status else None} "
                    f"- {mismatch.reason}"
                ),
                now=self._now(),
            )

        if mismatches:
            self._risk_repository.save(self._risk_id, self._risk_guard.state)

        return mismatches

    def run_cycle_once(self) -> TradingCycleResult | None:
        """Führt höchstens einen Trading-Zyklus aus.

        Gibt `None` zurück, wenn die Engine nicht läuft, der Kill-Switch
        aktiv ist, keine tatsächlich neue Kerze vorliegt, ein
        Sicherheitslimit den Zyklus blockiert hat, oder ein Fehler in einer
        der beteiligten Phasen aufgetreten ist (siehe Klassendocstring) -
        in all diesen Fällen wird `TradingOrchestrator.run_cycle()` gar
        nicht erst aufgerufen bzw. wurde bereits abgeschlossen, aber nicht
        vollständig persistiert. Ein `None`-Rückgabewert nach einem Fehler
        in der Persistenz-Phase bedeutet also nicht zwingend, dass keine
        Order ausgeführt wurde - der In-Memory-Portfolio-Zustand kann
        bereits eine reale Buchung enthalten, die erst beim nächsten
        erfolgreichen Zyklus gespeichert wird (siehe `CYCLE_ERROR`-Audit).
        """

        if self._risk_guard is None:
            raise RuntimeError("PaperTradingEngine wurde nicht gestartet (start() fehlt).")

        if not self._engine.status()["running"]:
            return None

        try:
            self._session.heartbeat_at = self._now()
            self._session_repository.save(self._session)
        except Exception as error:
            self._handle_cycle_error("heartbeat", error)
            return None

        if self._risk_guard.state.kill_switch_active:
            self._audit_log.record(
                self._session.session_id,
                AuditEventType.TRADE_BLOCKED,
                f"Kill-Switch aktiv: {self._risk_guard.state.kill_switch_reason}",
                now=self._now(),
            )
            return None

        try:
            candles = self._provider.get_candles(
                symbol=self._symbol,
                timeframe=self._timeframe,
                limit=self._candle_limit,
            )
            new_candles = self._store.add_many(candles)
        except Exception as error:
            self._handle_cycle_error("data_provider", error)
            return None

        if not new_candles:
            return None

        recent_candles = self._store.latest(self._symbol, self._candle_limit)
        current_price = recent_candles[-1].close

        try:
            guard_result = self._risk_guard.check(
                self._portfolio.export_state(),
                prices={self._symbol: current_price},
            )
            self._risk_repository.save(self._risk_id, self._risk_guard.state)
        except Exception as error:
            self._handle_cycle_error("risk_guard", error)
            return None

        if not guard_result.approved:
            event_type = (
                AuditEventType.RISK_EVENT
                if self._risk_guard.state.kill_switch_active
                else AuditEventType.TRADE_BLOCKED
            )
            self._audit_log.record(
                self._session.session_id, event_type, guard_result.reason, now=self._now()
            )
            return None

        try:
            result = self._orchestrator.run_cycle(recent_candles)
        except Exception as error:
            self._handle_cycle_error("orchestrator", error)
            return None

        try:
            self._record_execution_if_any(result)
            self._portfolio_repository.save(self._portfolio_id, self._portfolio.export_state())
        except Exception as error:
            self._handle_cycle_error("persistence", error)
            return None

        return result

    def _record_execution_if_any(self, result: TradingCycleResult) -> None:
        """Protokolliert die tatsächliche Ausführung, nicht die ursprünglich
        angefragte Order: `execution.filled_quantity` (die einzige
        authoritative Quelle für die tatsächlich gefüllte Menge - `execution.
        order.quantity` spiegelt nur die an den Broker gesendete, ggf. auf
        LOT_SIZE gerundete Anfrage, siehe `execution/live_broker.py`) mit
        Fallback auf `execution.order.quantity` für Broker ohne
        Teilausführungs-Unterscheidung (PaperBroker/MockLiveBroker -
        "Legacy", siehe `execution.models.derive_order_status()`), sowie
        `execution.order.price` (der echte durchschnittliche Fill-Preis,
        nicht der Signalzeit-Preis der ursprünglichen Order). `result.order`
        (die ursprüngliche Anfrage) bleibt zusätzlich im Audit-Event
        sichtbar - Intent und Execution nebeneinander, keines verdrängt das
        andere."""

        if result.execution is None:
            return

        order = result.order
        execution = result.execution
        actual_quantity = (
            execution.filled_quantity
            if execution.filled_quantity is not None
            else execution.order.quantity
        )
        actual_price = execution.order.price

        self._order_history.append(
            self._session.session_id,
            OrderExecution(
                timestamp=self._now(),
                symbol=order.symbol,
                side=order.side,
                quantity=actual_quantity,
                price=actual_price,
                fee=execution.fee,
                success=execution.success,
                client_order_id=order.client_order_id,
                broker_order_id=execution.broker_order_id,
                status=execution.status,
            ),
        )

        if execution.success:
            self._audit_log.record(
                self._session.session_id,
                AuditEventType.ORDER_EXECUTED,
                (
                    f"{order.side} angefragt={order.quantity}@{order.price} "
                    f"ausgeführt={actual_quantity}@{actual_price} {order.symbol}"
                ),
                now=self._now(),
            )

    def _handle_cycle_error(self, phase: str, error: Exception) -> None:
        message = f"Fehler in Phase '{phase}': {error}"
        self._last_error = message
        logger.error("Zyklus-Fehler in Session {}: {}", self._session.session_id, message)

        try:
            self._audit_log.record(
                self._session.session_id, AuditEventType.CYCLE_ERROR, message, now=self._now()
            )
        except Exception:
            logger.error(
                "Audit-Log für CYCLE_ERROR ebenfalls fehlgeschlagen (Session {})",
                self._session.session_id,
            )

    def health(self) -> HealthSnapshot:
        """Aggregiert den aktuellen Betriebszustand - keine eigene
        Persistenz, siehe `paper_trading.health`."""

        return build_health_snapshot(
            session=self._session,
            trading_engine=self._engine,
            store=self._store,
            symbol=self._symbol,
            order_history=self._order_history,
            risk_state=self._risk_guard.state if self._risk_guard is not None else None,
            last_error=self._last_error,
        )

    def stop(self, reason: str = "Manuell gestoppt") -> None:
        """Speichert den aktuellen Zustand final, stoppt die `TradingEngine`
        und protokolliert den Stop-Grund."""

        self._portfolio_repository.save(self._portfolio_id, self._portfolio.export_state())
        if self._risk_guard is not None:
            self._risk_repository.save(self._risk_id, self._risk_guard.state)

        self._session.stopped_at = self._now()
        self._session.status = "stopped"
        self._session_repository.save(self._session)

        self._engine.stop()
        self._audit_log.record(
            self._session.session_id, AuditEventType.SESSION_STOPPED, reason, now=self._now()
        )
        logger.info("Paper-Trading-Session gestoppt: {} ({})", self._session.session_id, reason)
