"""Datenmodelle der Trading-Orchestrierung."""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.execution.models import ExecutionResult, Order
from tradingbot.risk.models import RiskDecision
from tradingbot.strategy.models import TradingSignal


@dataclass
class TradingCycleResult:
    """Ergebnis eines vollständigen Paper-Trading-Zyklus.

    `order` und `execution` sind `None`, wenn das Risiko-System das Signal
    nicht genehmigt hat - in diesem Fall wurde weder eine Order erzeugt noch
    der Broker aufgerufen.
    """

    signal: TradingSignal
    decision: RiskDecision
    order: Order | None
    execution: ExecutionResult | None
