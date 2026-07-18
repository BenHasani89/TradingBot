"""Repository-Schnittstelle für die Persistenz von Session-Metadaten."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradingbot.paper_trading.session import SessionMetadata


class SessionRepository(ABC):
    """Abstrakte Persistenz-Schnittstelle für `SessionMetadata`.

    Kennt ausschliesslich das Speichern/Laden einer Session anhand ihrer
    `session_id` - keine Kenntnis von Portfolio- oder Risk-State, keine
    Vermischung mit `PortfolioRepository`/`RiskStateRepository`.
    """

    @abstractmethod
    def save(self, session: SessionMetadata) -> None:
        """Speichert `session` vollständig, überschreibt einen zuvor
        gespeicherten Zustand mit derselben `session_id`."""

    @abstractmethod
    def load(self, session_id: str) -> SessionMetadata | None:
        """Lädt die zuletzt gespeicherte Session für `session_id`.

        Gibt `None` zurück, wenn für `session_id` noch nichts gespeichert
        wurde.
        """
