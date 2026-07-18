"""Aggregation von Out-of-Sample-Ergebnissen über mehrere Walk-Forward-Fenster.

Reine Auswertung bereits berechneter `WalkForwardWindowResult`-Objekte (keine
erneute Backtest-Ausführung), nur Standardbibliothek (`statistics`).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from tradingbot.backtest.walk_forward import WalkForwardWindowResult


@dataclass
class WalkForwardSummary:
    """Zusammenfassung der Out-of-Sample-Ergebnisse über alle Fenster."""

    window_count: int
    average_out_of_sample_performance_percent: float
    average_out_of_sample_sharpe_ratio: float
    performance_std_dev: float
    profitable_window_ratio_percent: float


def aggregate_walk_forward_results(
    results: list[WalkForwardWindowResult],
) -> WalkForwardSummary:
    """Fasst die Out-of-Sample-Ergebnisse aller Fenster zu einer Übersicht zusammen.

    Nutzt ausschliesslich die bereits pro Fenster berechneten
    `out_of_sample_result`-Kennzahlen. Gibt eine Zusammenfassung mit lauter
    `0.0`-Werten zurück, wenn `results` leer ist.
    """

    if not results:
        return WalkForwardSummary(
            window_count=0,
            average_out_of_sample_performance_percent=0.0,
            average_out_of_sample_sharpe_ratio=0.0,
            performance_std_dev=0.0,
            profitable_window_ratio_percent=0.0,
        )

    performances = [r.out_of_sample_result.performance_percent for r in results]
    sharpe_ratios = [r.out_of_sample_result.sharpe_ratio for r in results]
    profitable_windows = sum(1 for p in performances if p > 0)

    return WalkForwardSummary(
        window_count=len(results),
        average_out_of_sample_performance_percent=statistics.mean(performances),
        average_out_of_sample_sharpe_ratio=statistics.mean(sharpe_ratios),
        performance_std_dev=statistics.stdev(performances) if len(performances) >= 2 else 0.0,
        profitable_window_ratio_percent=profitable_windows / len(results) * 100,
    )
