"""Laufzeit-Zustand für portfolio-bezogene Sicherheitslimits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class RiskState:
    """Persistenter Zustand des `PortfolioRiskGuard`.

    Unterscheidet explizit zwischen dem permanenten `kill_switch_active`
    (ausschliesslich manueller Reset, ausgelöst z. B. durch Maximum
    Drawdown) und dem temporären `daily_loss_blocked` (automatischer Reset
    beim nächsten Tageswechsel, ausgelöst durch das Daily Loss Limit) -
    beide Zustände dürfen nicht in ein einzelnes Flag zusammengefasst
    werden, da sie unterschiedlich zurückgesetzt werden.
    """

    day_start_equity: float
    day_start_date: date
    peak_equity: float
    kill_switch_active: bool = False
    kill_switch_reason: str | None = None
    daily_loss_blocked: bool = False
    daily_loss_reason: str | None = None
