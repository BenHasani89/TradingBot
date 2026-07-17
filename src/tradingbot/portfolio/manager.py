"""Portfolio-Verwaltung des Trading-Bots."""

from tradingbot.portfolio.models import (
    PortfolioStatus,
    Position,
)


class PortfolioManager:
    """Verwaltet Kapital und Positionen."""

    def __init__(self, initial_capital: float) -> None:
        self._capital = initial_capital
        self._positions: list[Position] = []

    def add_position(
        self,
        symbol: str,
        quantity: float,
        price: float,
    ) -> None:
        """Fügt eine Position hinzu."""

        self._positions.append(
            Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
            )
        )

    def status(self) -> PortfolioStatus:
        """Gibt aktuellen Portfolio-Status zurück."""

        return PortfolioStatus(
            capital=self._capital,
            positions=self._positions,
        )
