"""Trading-Orchestrierung: verbindet Marktdaten, Strategie, Risiko-Prüfung,
Order-Ausführung und Portfolio zu einem vollständigen Paper-Trading-Zyklus.
"""

from __future__ import annotations

from typing import cast

from loguru import logger

from tradingbot.core.engine import TradingEngine
from tradingbot.core.models import TradingCycleResult
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import PaperBroker
from tradingbot.execution.models import Order, OrderSide
from tradingbot.execution.order_manager import OrderManager
from tradingbot.execution.order_repository import InMemoryOrderRepository, OrderRepository
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.base import Strategy


class TradingOrchestrator:
    """Führt einen vollständigen Paper-Trading-Zyklus aus.

    Verbindet Strategie, Risiko-Prüfung, Order-Ausführung (`PaperBroker`) und
    Portfolio-Buchung. Führt nur dann etwas aus, wenn die übergebene
    `TradingEngine` aktiv ist (`start()` wurde aufgerufen) - andernfalls wird
    kein Marktzugriff simuliert und kein Trade gebucht.

    Enthält keine echte Börsen-Anbindung und kein Live-Trading; alle
    Ausführungen laufen ausschliesslich über den simulierten `PaperBroker`.
    """

    def __init__(
        self,
        engine: TradingEngine,
        strategy: Strategy,
        risk_manager: RiskManager,
        portfolio: PortfolioManager,
        broker: PaperBroker,
        order_repository: OrderRepository | None = None,
    ) -> None:
        self._engine = engine
        self._strategy = strategy
        self._risk_manager = risk_manager
        self._portfolio = portfolio
        self._broker = broker
        # Additiver Injection-Punkt: bleibt `order_repository` weg (alle
        # Backtest-/Research-Aufrufer, alle bisherigen Tests), verhält sich
        # der Orchestrator exakt wie zuvor - `InMemoryOrderRepository`, kein
        # SQLite-Schreibvorgang pro simuliertem Trade. Der `OrderManager`
        # bleibt in jedem Fall im Besitz des Orchestrators und an denselben
        # `broker` gebunden wie der Cash-Check weiter unten - ein separat
        # injizierter, fertiger `OrderManager` könnte sonst versehentlich an
        # einen anderen Broker gebunden sein.
        repository = order_repository if order_repository is not None else InMemoryOrderRepository()
        self._order_manager = OrderManager(broker=broker, repository=repository)

    def run_cycle(self, candles: list[MarketCandle]) -> TradingCycleResult:
        """Führt einen Trading-Zyklus für die übergebenen Kerzen aus.

        Ablauf: Strategie analysiert die Kerzen -> Risiko-System prüft das
        Signal -> bei Genehmigung wird eine Order erzeugt, über den
        `PaperBroker` ausgeführt und bei Erfolg im Portfolio gebucht.

        Args:
            candles: Kerzen eines einzelnen Symbols, chronologisch sortiert.
                Muss mindestens so viele Kerzen enthalten, wie die verwendete
                Strategie für eine Analyse benötigt.

        Returns:
            Ergebnis des Zyklus. `order`/`execution` sind `None`, wenn das
            Signal nicht genehmigt wurde oder - bei BUY - nicht genügend
            Kapital im Portfolio verfügbar ist (siehe
            `PortfolioManager.available_cash()`). Ein Trade kann so nie
            negatives Kapital erzeugen; der `PaperBroker` wird in diesem
            Fall gar nicht erst aufgerufen.

        Raises:
            RuntimeError: wenn die `TradingEngine` nicht aktiv ist.
        """

        if not self._engine.status()["running"]:
            raise RuntimeError(
                "TradingEngine ist nicht aktiv - Zyklus wird nicht ausgeführt."
            )

        signal = self._strategy.analyze(candles)
        decision = self._risk_manager.evaluate(signal)

        if not decision.approved:
            logger.info("Zyklus ohne Order beendet: {}", decision.reason)
            return TradingCycleResult(
                signal=signal,
                decision=decision,
                order=None,
                execution=None,
                closed_trade=None,
            )

        # Das Risiko-System lehnt HOLD-Signale immer ab (siehe RiskManager),
        # daher ist an dieser Stelle ausschliesslich BUY oder SELL möglich.
        if signal.signal not in ("BUY", "SELL"):
            raise RuntimeError(
                f"Unerwartetes genehmigtes Signal ohne Handelsrichtung: {signal.signal}"
            )
        side = cast(OrderSide, signal.signal)

        current_price = candles[-1].close
        quantity = decision.position_size / current_price

        if side == "BUY":
            # Exakte Vorhersage des Kapitalbedarfs inkl. Slippage und
            # Gebühr - derselbe Fill-Preis, den der Broker intern berechnet
            # (siehe PaperBroker.execute), damit die Kapitalprüfung auch bei
            # aktivierten Kosten nicht unterschätzt wird.
            expected_fill_price = current_price * (1 + self._broker.slippage_percent)
            required_cash = quantity * expected_fill_price * (1 + self._broker.fee_percent)
            available_cash = self._portfolio.available_cash()
            if required_cash > available_cash:
                logger.info(
                    "Zyklus ohne Order beendet: nicht genügend Kapital "
                    "(benötigt {}, verfügbar {})",
                    required_cash,
                    available_cash,
                )
                return TradingCycleResult(
                    signal=signal,
                    decision=decision,
                    order=None,
                    execution=None,
                    closed_trade=None,
                )

        order = Order(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            price=current_price,
        )

        execution = self._order_manager.submit(order)
        closed_trade = None

        if execution.success:
            filled_order = execution.order

            # Portfolio kennt weder Gebühren noch Slippage (unveränderte
            # Schnittstelle) - daher wird hier ein einzelner effektiver
            # Preis gebildet, der Fill-Preis (bereits inkl. Slippage) und
            # Gebühr zu einem korrekten Netto-Kapitaleffekt zusammenfasst.
            # Gebühr/Slippage bleiben trotzdem separat im ExecutionResult
            # sichtbar (siehe execution.fee / execution.slippage).
            if filled_order.side == "BUY":
                total_cash_impact = (
                    filled_order.price * filled_order.quantity + execution.fee
                )
            else:
                total_cash_impact = (
                    filled_order.price * filled_order.quantity - execution.fee
                )
            effective_price = total_cash_impact / filled_order.quantity

            closed_trade = self._portfolio.apply_trade(
                symbol=filled_order.symbol,
                side=filled_order.side,
                quantity=filled_order.quantity,
                price=effective_price,
            )
            logger.info(
                "Trade gebucht: {} {} {} @ {} (Fill {}, Gebühr {}, Slippage {})",
                filled_order.side,
                filled_order.quantity,
                filled_order.symbol,
                effective_price,
                filled_order.price,
                execution.fee,
                execution.slippage,
            )

        return TradingCycleResult(
            signal=signal,
            decision=decision,
            order=order,
            execution=execution,
            closed_trade=closed_trade,
        )
