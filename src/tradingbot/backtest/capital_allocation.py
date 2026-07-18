"""Kapitalallokation für die Portfolio-Simulation.

Bewusst einfach gehalten: feste Gleichgewichtung über alle Assets, einmalig
aus dem Startkapital berechnet. Keine dynamische Gewichtung, keine
Optimierung, keine Rebalancing-Logik (eigene, spätere Phase).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapitalAllocator:
    """Teilt verfügbares Kapital gleichmässig auf mehrere Assets auf."""

    def allocation_for(self, symbols: list[str], capital: float) -> dict[str, float]:
        """Gibt für jedes Symbol denselben Anteil des Kapitals zurück.

        Bei `n` Symbolen bekommt jedes exakt `capital / n`. Gibt ein leeres
        Dictionary zurück (keine Ausnahme), wenn `symbols` leer ist.
        """

        if not symbols:
            return {}

        share = capital / len(symbols)
        return {symbol: share for symbol in symbols}
