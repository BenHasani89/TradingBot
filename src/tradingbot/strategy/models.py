"""Datenmodelle für Trading-Signale."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SignalType = Literal["BUY", "SELL", "HOLD"]


@dataclass
class TradingSignal:
    """Ein von einer Strategie erzeugtes Signal."""

    symbol: str
    signal: SignalType
    confidence: float
