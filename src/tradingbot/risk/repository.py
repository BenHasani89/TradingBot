"""Repository-Schnittstelle für die Persistenz des Risk-Zustands."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradingbot.risk.risk_state import RiskState


class RiskStateRepository(ABC):
    """Abstrakte Persistenz-Schnittstelle für `RiskState`.

    Kennt ausschliesslich das Speichern/Laden eines vollständigen
    Zustands-Snapshots je `risk_id` - keine Risikologik, keine Kenntnis von
    `PortfolioRiskGuard`-internen Details.
    """

    @abstractmethod
    def save(self, risk_id: str, state: RiskState) -> None:
        """Speichert `state` als vollständigen Snapshot für `risk_id`.

        Ersetzt einen zuvor gespeicherten Zustand vollständig (kein
        inkrementelles Update).
        """

    @abstractmethod
    def load(self, risk_id: str) -> RiskState | None:
        """Lädt den zuletzt gespeicherten Zustand für `risk_id`.

        Gibt `None` zurück, wenn für `risk_id` noch nichts gespeichert
        wurde.
        """
