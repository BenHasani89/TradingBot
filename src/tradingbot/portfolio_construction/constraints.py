"""Portfolio Constraints: einfache Grenzen für Ziel-Allokationen.

Reine Validierung/Kappung bereits berechneter Ziel-Gewichte - trifft selbst
keine Allokationsentscheidung. `min_assets` wird geprüft, aber (da es keine
eindeutige automatische Korrektur gibt) nicht automatisch behoben - nur
`max_weight_per_asset` wird aktiv gekappt.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.portfolio_construction.models import ConstraintAdjustment


@dataclass
class PortfolioConstraints:
    """Prüft/kappt Ziel-Gewichte. Übergewicht wird auf `max_weight_per_asset`
    gekappt; überschüssiges Kapital bleibt unverteiltes Cash (keine
    automatische Neuverteilung auf andere Assets in dieser Version).
    """

    max_weight_per_asset: float = 1.0
    min_assets: int = 1

    def apply(
        self,
        weights: dict[str, float],
    ) -> tuple[dict[str, float], list[ConstraintAdjustment]]:
        """Wendet die Constraints an.

        Returns:
            Ein Tupel aus den (ggf. gekappten) Gewichten und einer Liste der
            vorgenommenen Anpassungen (leer, wenn alles bereits
            regelkonform war).
        """

        adjusted: dict[str, float] = {}
        adjustments: list[ConstraintAdjustment] = []

        for symbol, weight in weights.items():
            if weight > self.max_weight_per_asset:
                adjustments.append(
                    ConstraintAdjustment(
                        symbol=symbol,
                        original_weight=weight,
                        adjusted_weight=self.max_weight_per_asset,
                        reason=f"max_weight_per_asset ({self.max_weight_per_asset}) überschritten",
                    )
                )
                adjusted[symbol] = self.max_weight_per_asset
            else:
                adjusted[symbol] = weight

        return adjusted, adjustments
