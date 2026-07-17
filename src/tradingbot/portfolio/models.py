"""Datenmodelle für das Portfolio-System."""

from dataclasses import dataclass


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
