"""Ranking mehrerer Backtest-Ergebnisse nach risikoadjustierten und
trade-basierten Kennzahlen.

Reine Auswertung bereits vorhandener `BacktestResult`-Objekte - keine
Optimierungslogik/-bibliothek, kein Parameter-Suchalgorithmus. Die eigentliche
Parametervielfalt entsteht über `backtest/parameter_grid.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.backtest.metrics import (
    annualized_return_percent,
    calmar_ratio,
    sharpe_ratio,
    volatility_percent,
)
from tradingbot.backtest.models import BacktestResult
from tradingbot.backtest.trade_ledger import (
    average_trade,
    extract_closed_trades,
    payoff_ratio,
    profit_factor,
    win_rate_percent,
)


@dataclass
class RankedResult:
    """Eine Zeile im Strategie-Ranking mit allen verfügbaren Kennzahlen.

    `trades` zählt hier - anders als `BacktestResult.trades` (Order-
    Ausführungen) - die Anzahl **abgeschlossener** (realisierter) Trades,
    konsistent mit `win_rate_percent`/`profit_factor`/`average_trade`/
    `payoff_ratio`, die alle auf derselben Grundlage berechnet werden.
    """

    strategy_name: str

    # Performance
    performance_percent: float
    annualized_return_percent: float

    # Risiko
    sharpe_ratio: float
    volatility_percent: float
    max_drawdown_percent: float
    calmar_ratio: float

    # Trade-Qualität
    trades: int
    win_rate_percent: float
    profit_factor: float
    average_trade: float
    payoff_ratio: float


def _initial_capital_from_result(result: BacktestResult) -> float:
    """Rekonstruiert das ursprüngliche Startkapital aus einem `BacktestResult`.

    `BacktestResult` speichert das Startkapital nicht direkt - wohl aber
    `profit_loss` (Endwert − Startkapital) und den Endwert implizit in
    `equity_curve[-1].total_value`. Bei leerer Equity-Kurve wird `0.0`
    zurückgegeben; in diesem Fall liefern alle equity-kurven-basierten
    Kennzahlen ohnehin ihren definierten Leerfall-Wert, unabhängig vom
    Startkapital.
    """

    if not result.equity_curve:
        return 0.0

    return result.equity_curve[-1].total_value - result.profit_loss


def rank_strategies(
    results: dict[str, BacktestResult],
    periods_per_year: int,
    sort_by: str = "sharpe_ratio",
) -> list[RankedResult]:
    """Berechnet für jedes `BacktestResult` alle Kennzahlen und sortiert
    absteigend nach `sort_by`.

    Voraussetzung für einen fairen Vergleich: alle `results` stammen aus
    Backtests auf denselben historischen Kerzen mit gleichem Startkapital
    und gleichen Risiko-Einstellungen (z. B. über `BacktestResearchRunner`).

    Args:
        results: Zuordnung von Strategie-Name zu `BacktestResult`.
        periods_per_year: Anzahl Kerzen-Perioden pro Jahr (z. B. `8760` für
            Stundenkerzen bei einem 24/7-Markt) - wird für die annualisierten
            Kennzahlen benötigt und nicht aus den Daten abgeleitet.
        sort_by: Name eines numerischen `RankedResult`-Felds, nach dem
            absteigend sortiert wird. Standard `"sharpe_ratio"`.

    Returns:
        Eine `RankedResult`-Zeile je Strategie, absteigend nach `sort_by`
        sortiert.

    Raises:
        AttributeError: wenn `sort_by` kein gültiges Feld von `RankedResult`
            ist.
    """

    ranked: list[RankedResult] = []

    for name, result in results.items():
        initial_capital = _initial_capital_from_result(result)
        closed_trades = extract_closed_trades(result.cycle_results)

        ranked.append(
            RankedResult(
                strategy_name=name,
                performance_percent=result.performance_percent,
                annualized_return_percent=annualized_return_percent(
                    result.equity_curve, initial_capital, periods_per_year
                ),
                sharpe_ratio=sharpe_ratio(result.equity_curve, periods_per_year),
                volatility_percent=volatility_percent(result.equity_curve, periods_per_year),
                max_drawdown_percent=result.max_drawdown_percent,
                calmar_ratio=calmar_ratio(result.equity_curve, initial_capital, periods_per_year),
                trades=len(closed_trades),
                win_rate_percent=win_rate_percent(closed_trades),
                profit_factor=profit_factor(closed_trades),
                average_trade=average_trade(closed_trades),
                payoff_ratio=payoff_ratio(closed_trades),
            )
        )

    return sorted(ranked, key=lambda row: getattr(row, sort_by), reverse=True)
