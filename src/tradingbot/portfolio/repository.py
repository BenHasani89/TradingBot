"""Repository-Schnittstelle für die Persistenz des Portfolio-Zustands."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradingbot.portfolio.models import PortfolioStatus


class PortfolioRepository(ABC):
    """Abstrakte Persistenz-Schnittstelle für `PortfolioStatus`.

    Kennt ausschliesslich das Speichern/Laden eines vollständigen
    Zustands-Snapshots je `portfolio_id` - keine Trading-Logik, keine
    Kenntnis von `PortfolioManager`-internen Details.
    """

    @abstractmethod
    def save(self, portfolio_id: str, state: PortfolioStatus) -> None:
        """Speichert `state` als vollständigen Snapshot für `portfolio_id`.

        Ersetzt einen zuvor gespeicherten Zustand vollständig (kein
        inkrementelles Update).
        """

    @abstractmethod
    def load(self, portfolio_id: str) -> PortfolioStatus | None:
        """Lädt den zuletzt gespeicherten Zustand für `portfolio_id`.

        Gibt `None` zurück, wenn für `portfolio_id` noch nichts gespeichert
        wurde.
        """
