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

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence muss zwischen 0.0 und 1.0 liegen, war {self.confidence}"
            )
