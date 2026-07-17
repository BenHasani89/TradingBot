"""Modelle für Risiko-Verwaltung."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskDecision:
    """Ergebnis einer Risiko-Prüfung."""

    approved: bool
    position_size: float
    reason: str
