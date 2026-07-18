"""Aggregation und robuste Parameterbewertung über mehrere Assets hinweg.

Reine Auswertung bereits berechneter `BacktestResult`-Objekte (keine erneute
Backtest-Ausführung), nur Standardbibliothek (`statistics`). Baut auf
`optimization.rank_strategies()` auf, das je Asset mit dessen eigenem
`periods_per_year` aufgerufen wird - unterschiedliche Assets (z. B. 24/7-
Krypto vs. Börsenzeiten-Aktien) benötigen unterschiedliche Annualisierung.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from tradingbot.backtest.models import BacktestResult
from tradingbot.backtest.optimization import RankedResult, rank_strategies


@dataclass
class MultiAssetSummary:
    """Zusammenfassung eines Backtest-Ergebnisses über mehrere Assets."""

    asset_count: int
    average_performance_percent: float
    average_sharpe_ratio: float
    performance_std_dev: float
    profitable_asset_ratio_percent: float


@dataclass
class ParameterRobustnessResult:
    """Bewertung einer Parameter-Kombination über mehrere Assets hinweg."""

    strategy_name: str
    summary: MultiAssetSummary
    results_by_asset: dict[str, RankedResult]


def _summarize(ranked_per_asset: list[RankedResult]) -> MultiAssetSummary:
    if not ranked_per_asset:
        return MultiAssetSummary(
            asset_count=0,
            average_performance_percent=0.0,
            average_sharpe_ratio=0.0,
            performance_std_dev=0.0,
            profitable_asset_ratio_percent=0.0,
        )

    performances = [r.performance_percent for r in ranked_per_asset]
    sharpe_ratios = [r.sharpe_ratio for r in ranked_per_asset]
    profitable = sum(1 for p in performances if p > 0)

    return MultiAssetSummary(
        asset_count=len(ranked_per_asset),
        average_performance_percent=statistics.mean(performances),
        average_sharpe_ratio=statistics.mean(sharpe_ratios),
        performance_std_dev=statistics.stdev(performances) if len(performances) >= 2 else 0.0,
        profitable_asset_ratio_percent=profitable / len(ranked_per_asset) * 100,
    )


def aggregate_multi_asset_results(
    results: dict[str, BacktestResult],
    periods_per_year: dict[str, int],
) -> MultiAssetSummary:
    """Fasst `BacktestResult`-Objekte mehrerer Assets zu einer Übersicht zusammen.

    Args:
        results: Zuordnung von Symbol zu `BacktestResult` (z. B. Ergebnis von
            `MultiAssetResearchRunner.run()`).
        periods_per_year: Perioden pro Jahr je Symbol - muss für jedes in
            `results` vorkommende Symbol einen Eintrag enthalten.

    Returns:
        Eine `MultiAssetSummary` mit lauter `0.0`-Werten, wenn `results` leer ist.
    """

    if not results:
        return _summarize([])

    ranked_per_asset = [
        rank_strategies({symbol: result}, periods_per_year[symbol])[0]
        for symbol, result in results.items()
    ]

    return _summarize(ranked_per_asset)


def rank_parameter_sets_by_robustness(
    results_by_variant: dict[str, dict[str, BacktestResult]],
    periods_per_year: dict[str, int],
    sort_by: str = "average_sharpe_ratio",
) -> list[ParameterRobustnessResult]:
    """Bewertet mehrere Parameter-Varianten anhand ihrer durchschnittlichen
    Performance über mehrere Assets und sortiert absteigend nach `sort_by`.

    Bevorzugt Parameter-Sets, die auf **mehreren** Assets konsistent
    funktionieren, gegenüber Sets mit einem einzelnen Spitzenwert auf nur
    einem Asset - der eigentliche Zweck robuster Parameterbewertung.

    Args:
        results_by_variant: Zuordnung von Parameter-Varianten-Label (z. B.
            aus `parameter_grid.build_strategy_variants()`) zu einer
            Zuordnung von Symbol zu `BacktestResult` - das Ergebnis, mehrfach
            `MultiAssetResearchRunner.run()` mit unterschiedlichen
            Strategie-Parametern aufzurufen.
        periods_per_year: Perioden pro Jahr je Symbol.
        sort_by: Name eines numerischen `MultiAssetSummary`-Felds (nicht
            `RankedResult`!). Standard `"average_sharpe_ratio"`.

    Returns:
        Eine `ParameterRobustnessResult`-Zeile je Variante, absteigend nach
        `sort_by` sortiert - das robusteste Parameter-Set steht vorne.

    Raises:
        AttributeError: wenn `sort_by` kein gültiges Feld von
            `MultiAssetSummary` ist.
    """

    ranked: list[ParameterRobustnessResult] = []

    for variant_label, results_by_symbol in results_by_variant.items():
        results_by_asset = {
            symbol: rank_strategies({symbol: result}, periods_per_year[symbol])[0]
            for symbol, result in results_by_symbol.items()
        }
        summary = _summarize(list(results_by_asset.values()))

        ranked.append(
            ParameterRobustnessResult(
                strategy_name=variant_label,
                summary=summary,
                results_by_asset=results_by_asset,
            )
        )

    return sorted(ranked, key=lambda row: getattr(row.summary, sort_by), reverse=True)
