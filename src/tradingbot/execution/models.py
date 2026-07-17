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
    """Ergebnis einer Order-Ausführung.

    `fee` und `slippage` sind absolute Kostenbeträge (nicht Prozentwerte),
    getrennt ausgewiesen statt im Preis versteckt - Voraussetzung für eine
    spätere Brutto/Fees/Slippage/Netto-Auswertung. Bei kostenfreier
    Ausführung sind beide `0.0`.
    """

    success: bool
    order: Order
    message: str
    fee: float
    slippage: float
