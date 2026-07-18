"""Ranking mehrerer Portfolio-Construction-Ergebnisse nach risikoadjustierten
Kennzahlen.

Bewusst NICHT durch Erweiterung von `optimization.rank_strategies()` gelöst:
diese ist hart von `result.cycle_results` (Strategy-Trades) abhängig, das
`PortfolioConstructionResult` nicht besitzt (kein Strategy-System beteiligt).
Stattdessen eine eigene, kleinere Funktion mit Rebalancing-eigenen statt
Trade-eigenen Kennzahlen. `metrics.py` wird dabei unverändert wiederverwendet.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.backtest.metrics import (
    annualized_return_percent,
    calmar_ratio,
    sharpe_ratio,
    volatility_percent,
)
from tradingbot.backtest.portfolio_construction_engine import PortfolioConstructionResult


@dataclass
class PortfolioConstructionRankedResult:
    """Eine Zeile im Portfolio-Construction-Ranking mit allen verfügbaren
    Kennzahlen."""

    configuration_name: str
    performance_percent: float
    annualized_return_percent: float
    sharpe_ratio: float
    volatility_percent: float
    max_drawdown_percent: float
    calmar_ratio: float
    rebalancing_count: int
    turnover_percent: float


def _initial_capital_from_result(result: PortfolioConstructionResult) -> float:
    """Rekonstruiert das ursprüngliche Startkapital aus einem
    `PortfolioConstructionResult` (analog zu
    `optimization._initial_capital_from_result`): `PortfolioConstructionResult`
    speichert das Startkapital nicht direkt, wohl aber `profit_loss` und den
    Endwert implizit in `equity_curve[-1]`.
    """

    if not result.equity_curve:
        return 0.0

    return result.equity_curve[-1].total_value - result.profit_loss


def _turnover_percent(result: PortfolioConstructionResult) -> float:
    """Durchschnittliches gehandeltes Volumen je Rebalancing-Ereignis, als
    Anteil (Prozent) des Portfolio-Werts zum jeweiligen Zeitpunkt.

    `0.0`, wenn nie rebalanciert wurde.
    """

    if not result.rebalancing_events:
        return 0.0

    turnovers: list[float] = []
    for event in result.rebalancing_events:
        traded_value = sum(trade.quantity * trade.price for trade in event.trades)
        # equity_curve[k] entspricht Zeitschritt i=k+1 (siehe
        # PortfolioConstructionEngine.run() - Aufzeichnung beginnt bei i=1).
        portfolio_value = result.equity_curve[event.step_index - 1].total_value
        if portfolio_value:
            turnovers.append(traded_value / portfolio_value * 100)

    if not turnovers:
        return 0.0

    return sum(turnovers) / len(turnovers)


def rank_portfolio_configurations(
    results: dict[str, PortfolioConstructionResult],
    periods_per_year: int,
    sort_by: str = "sharpe_ratio",
) -> list[PortfolioConstructionRankedResult]:
    """Berechnet für jedes `PortfolioConstructionResult` alle Kennzahlen und
    sortiert absteigend nach `sort_by`.

    Args:
        results: Zuordnung von Konfigurations-Name zu `PortfolioConstructionResult`.
        periods_per_year: Anzahl Kerzen-Perioden pro Jahr - für die
            annualisierten Kennzahlen benötigt, nicht aus den Daten abgeleitet.
        sort_by: Name eines numerischen `PortfolioConstructionRankedResult`-Felds.
            Standard `"sharpe_ratio"`.

    Returns:
        Eine Zeile je Konfiguration, absteigend nach `sort_by` sortiert.

    Raises:
        AttributeError: wenn `sort_by` kein gültiges Feld ist.
    """

    ranked: list[PortfolioConstructionRankedResult] = []

    for name, result in results.items():
        initial_capital = _initial_capital_from_result(result)

        ranked.append(
            PortfolioConstructionRankedResult(
                configuration_name=name,
                performance_percent=result.performance_percent,
                annualized_return_percent=annualized_return_percent(
                    result.equity_curve, initial_capital, periods_per_year
                ),
                sharpe_ratio=sharpe_ratio(result.equity_curve, periods_per_year),
                volatility_percent=volatility_percent(result.equity_curve, periods_per_year),
                max_drawdown_percent=result.max_drawdown_percent,
                calmar_ratio=calmar_ratio(result.equity_curve, initial_capital, periods_per_year),
                rebalancing_count=len(result.rebalancing_events),
                turnover_percent=_turnover_percent(result),
            )
        )

    return sorted(ranked, key=lambda row: getattr(row, sort_by), reverse=True)
