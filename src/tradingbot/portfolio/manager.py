"""Portfolio-Verwaltung des Trading-Bots."""

from tradingbot.portfolio.models import (
    PortfolioStatus,
    Position,
    TradeSide,
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

    def available_cash(self) -> float:
        """Gibt das aktuell verfügbare Kapital (Cash) zurück.

        Zentrale Abfragestelle für Kapitalprüfungen (z. B. durch den
        `TradingOrchestrator` vor einer Order-Erstellung).
        """

        return self._capital

    def apply_trade(
        self,
        symbol: str,
        side: TradeSide,
        quantity: float,
        price: float,
    ) -> None:
        """Bucht einen bereits ausgeführten Trade auf Kapital und Positionen.

        Neutral gegenüber dem Ausführungssystem: nimmt einfache Trade-Daten
        entgegen statt eines `execution.models.Order`, damit das
        Portfolio-System unabhängig vom Broker bleibt (siehe
        `tradingbot.portfolio.models.TradeSide`). Die Übersetzung von einer
        Order zu diesen Parametern übernimmt die Orchestrierung.

        Bei BUY wird das Kapital um `quantity * price` reduziert und die
        Position angelegt bzw. per Mengen-gewichtetem Durchschnittspreis
        erhöht. Bei SELL wird das Kapital entsprechend erhöht und die
        bestehende Position reduziert bzw. bei vollständigem Verkauf entfernt.
        Ein SELL ohne bestehende Position bucht nur das Kapital (kein
        Leerverkauf-Tracking).
        """

        if side == "BUY":
            self._capital -= quantity * price
            self._increase_position(symbol, quantity, price)
        else:
            self._capital += quantity * price
            self._decrease_position(symbol, quantity)

    def _increase_position(
        self,
        symbol: str,
        quantity: float,
        price: float,
    ) -> None:
        for position in self._positions:
            if position.symbol == symbol:
                total_quantity = position.quantity + quantity
                position.entry_price = (
                    position.entry_price * position.quantity + price * quantity
                ) / total_quantity
                position.quantity = total_quantity
                return

        self._positions.append(
            Position(symbol=symbol, quantity=quantity, entry_price=price)
        )

    def _decrease_position(
        self,
        symbol: str,
        quantity: float,
    ) -> None:
        for position in self._positions:
            if position.symbol == symbol:
                position.quantity -= quantity
                if position.quantity <= 0:
                    self._positions.remove(position)
                return
