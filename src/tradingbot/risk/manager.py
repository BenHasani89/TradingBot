"""Risiko-Management für Trading-Entscheidungen."""

from __future__ import annotations

from tradingbot.risk.models import RiskDecision
from tradingbot.strategy.models import TradingSignal


class RiskManager:
    """Prüft, ob ein Trade erlaubt ist."""

    def __init__(
        self,
        max_position_size: float = 1000.0,
    ) -> None:
        self.max_position_size = max_position_size

    def evaluate(
        self,
        signal: TradingSignal,
    ) -> RiskDecision:
        """Bewertet ein Trading-Signal."""

        if signal.signal == "HOLD":
            return RiskDecision(
                approved=False,
                position_size=0.0,
                reason="Kein Handelssignal",
            )

        if signal.confidence < 0.5:
            return RiskDecision(
                approved=False,
                position_size=0.0,
                reason="Confidence zu niedrig",
            )

        return RiskDecision(
            approved=True,
            position_size=self.max_position_size,
            reason="Risiko akzeptiert",
        )
