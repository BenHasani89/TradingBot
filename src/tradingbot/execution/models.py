"""Modelle für Order-Ausführung."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OrderSide = Literal["BUY", "SELL"]


@dataclass
class Order:
    """Eine Trading-Order."""

    symbol: str
    side: OrderSide
    quantity: float
    price: float


@dataclass
class ExecutionResult:
    """Ergebnis einer Order-Ausführung."""

    success: bool
    order: Order
    message: str
