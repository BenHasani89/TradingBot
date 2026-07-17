"""Datenmodelle für den Trading-Bot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarketCandle:
    """Eine einzelne Kurskerze."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
