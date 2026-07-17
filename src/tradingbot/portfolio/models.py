"""Datenmodelle für das Portfolio-System."""

from dataclasses import dataclass
from typing import Literal

TradeSide = Literal["BUY", "SELL"]
"""Handelsrichtung eines gebuchten Trades - bewusst unabhängig von
`execution.models.OrderSide` definiert, damit das Portfolio-System nicht vom
Ausführungssystem (Broker) abhängt."""


@dataclass
class Position:
    """Eine einzelne Trading-Position."""

    symbol: str
    quantity: float
    entry_price: float

    def value(self, current_price: float) -> float:
        """Aktueller Wert der Position."""
        return self.quantity * current_price


@dataclass
class ClosedTrade:
    """Ein abgeschlossener (realisierter) Trade.

    Entsteht, wenn ein SELL eine bestehende Position ganz oder teilweise
    reduziert. `quantity` ist die verkaufte Menge (nicht zwingend die
    gesamte Positionsgrösse), `entry_price` der zum Verkaufszeitpunkt
    gültige (mengengewichtete) Einstiegspreis der Position.
    """

    symbol: str
    quantity: float
    entry_price: float
    exit_price: float
    profit_loss: float


@dataclass
class PortfolioStatus:
    """Aktueller Zustand des Portfolios."""

    capital: float
    positions: list[Position]

    def total_value(self, prices: dict[str, float]) -> float:
        """Gesamtwert inklusive Positionen."""

        value = self.capital

        for position in self.positions:
            if position.symbol in prices:
                value += position.value(prices[position.symbol])

        return value
