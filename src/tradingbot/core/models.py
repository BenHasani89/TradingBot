"""Datenmodelle der Trading-Orchestrierung."""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.execution.models import ExecutionResult, Order
from tradingbot.portfolio.models import ClosedTrade
from tradingbot.risk.models import RiskDecision
from tradingbot.strategy.models import TradingSignal


@dataclass
class ExecutionCostEstimate:
    """Für die Kapitalprüfung vor einem BUY angenommene Kosten (Slippage,
    Gebühr) - unabhängig vom konkreten Broker.

    Ersetzt die frühere direkte Kopplung von `TradingOrchestrator` an
    `PaperBroker`-spezifische Properties (`slippage_percent`/`fee_percent`),
    die einer echten `Broker`-ABC-Implementierung (z. B. `MockLiveBroker`,
    künftig `LiveBroker`) fehlen würden. Der Standardwert (`0.0`/`0.0`)
    entspricht exakt dem bisherigen kostenfreien Verhalten.
    """

    fee_percent: float = 0.0
    slippage_percent: float = 0.0


@dataclass
class TradingCycleResult:
    """Ergebnis eines vollständigen Paper-Trading-Zyklus.

    `order` und `execution` sind `None`, wenn das Risiko-System das Signal
    nicht genehmigt hat oder nicht genügend Kapital verfügbar war - in
    diesem Fall wurde weder eine Order erzeugt noch der Broker aufgerufen.
    `closed_trade` ist nur bei einem SELL gesetzt, das eine bestehende
    Position tatsächlich reduziert hat (siehe
    `PortfolioManager.apply_trade`); bei BUY oder wenn keine Order zustande
    kam, ist es `None`.
    """

    signal: TradingSignal
    decision: RiskDecision
    order: Order | None
    execution: ExecutionResult | None
    closed_trade: ClosedTrade | None
