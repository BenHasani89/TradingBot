"""Portfolio-Verwaltung des Trading-Bots."""

from tradingbot.portfolio.models import (
    ClosedTrade,
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
    ) -> ClosedTrade | None:
        """Bucht einen bereits ausgeführten Trade auf Kapital und Positionen.

        Neutral gegenüber dem Ausführungssystem: nimmt einfache Trade-Daten
        entgegen statt eines `execution.models.Order`, damit das
        Portfolio-System unabhängig vom Broker bleibt (siehe
        `tradingbot.portfolio.models.TradeSide`). Die Übersetzung von einer
        Order zu diesen Parametern übernimmt die Orchestrierung.

        Bei BUY wird das Kapital um `quantity * price` reduziert und die
        Position angelegt bzw. per Mengen-gewichtetem Durchschnittspreis
        erhöht - `apply_trade` gibt in diesem Fall `None` zurück, da noch
        nichts realisiert wurde. Bei SELL wird das Kapital entsprechend
        erhöht und die bestehende Position reduziert bzw. bei vollständigem
        Verkauf entfernt; der davor gültige Einstiegspreis wird gelesen und
        als `ClosedTrade` mit dem realisierten Gewinn/Verlust zurückgegeben.
        Ein SELL ohne bestehende Position bucht nur das Kapital und gibt
        `None` zurück (kein Leerverkauf-Tracking).

        `PortfolioManager` speichert dabei selbst keine Trade-Historie - das
        Sammeln der zurückgegebenen `ClosedTrade`-Objekte ist Aufgabe der
        aufrufenden Schicht (siehe `TradingOrchestrator`).
        """

        if side == "BUY":
            self._capital -= quantity * price
            self._increase_position(symbol, quantity, price)
            return None

        self._capital += quantity * price
        entry_price = self._decrease_position(symbol, quantity)
        if entry_price is None:
            return None

        return ClosedTrade(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=price,
            profit_loss=(price - entry_price) * quantity,
        )

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
    ) -> float | None:
        """Reduziert eine bestehende Position und gibt deren bisherigen
        Einstiegspreis zurück (oder `None`, wenn keine Position existiert).
        """

        for position in self._positions:
            if position.symbol == symbol:
                entry_price = position.entry_price
                position.quantity -= quantity
                if position.quantity <= 0:
                    self._positions.remove(position)
                return entry_price
        return None
