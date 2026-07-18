"""Datenmodelle für Portfolio Construction (Ziel-Allokation, Rebalancing)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tradingbot.portfolio.models import TradeSide


@dataclass
class RebalancingTrade:
    """Eine aus einer Rebalancing-Entscheidung abgeleitete Order-**Absicht**
    - noch keine ausgeführte Order (siehe `generate_rebalancing_orders`).
    """

    symbol: str
    side: TradeSide
    quantity: float
    price: float


@dataclass
class RebalancingEvent:
    """Protokoll eines ausgelösten und tatsächlich ausgeführten
    Rebalancing-Zeitpunkts."""

    step_index: int
    timestamp: datetime
    target_weights: dict[str, float]
    trades: list[RebalancingTrade]


@dataclass
class ConstraintAdjustment:
    """Eine vorgenommene Korrektur, weil ein Ziel-Gewicht eine
    Portfolio-Constraint verletzt hat."""

    symbol: str
    original_weight: float
    adjusted_weight: float
    reason: str
