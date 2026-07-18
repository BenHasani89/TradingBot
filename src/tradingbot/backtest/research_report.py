"""Einheitliche ResearchReport-Schicht: fasst `BacktestResult`,
`PortfolioBacktestResult` und `PortfolioConstructionResult` zusammen, ohne
sie zu verändern und ohne ihre unterschiedlichen Bedeutungen zu vermischen.

Kernprinzip: nur Kennzahlen, deren Bedeutung über alle drei Quellen hinweg
identisch ist, leben im gemeinsamen `ResearchReport`-Kern (ausschliesslich
equity-kurven-basiert, über `metrics.py` berechnet). Alles Quellenspezifische
(Trade- vs. Rebalancing-Zahlen, feste vs. zeitvariable Allokation) steckt in
`details` - einer von drei nicht austauschbaren Detail-Typen, ausgewählt über
`source_type`. Das verhindert strukturell dieselbe Verwechslungsgefahr, die
"trades" bei `PortfolioConstructionResult` vs. den anderen beiden hätte.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tradingbot.backtest.metrics import (
    annualized_return_percent,
    calmar_ratio,
    sharpe_ratio,
    volatility_percent,
)
from tradingbot.backtest.models import BacktestResult, EquityPoint
from tradingbot.backtest.portfolio_construction_engine import PortfolioConstructionResult
from tradingbot.backtest.portfolio_engine import PortfolioBacktestResult
from tradingbot.backtest.trade_ledger import (
    average_trade,
    extract_closed_trades,
    payoff_ratio,
    profit_factor,
    win_rate_percent,
)
from tradingbot.backtest.utils import infer_initial_capital
from tradingbot.core.models import TradingCycleResult


class ResearchSourceType(Enum):
    """Kennzeichnet, aus welchem Backtest-Ergebnistyp ein `ResearchReport`
    erzeugt wurde."""

    STRATEGY_BACKTEST = "strategy_backtest"
    PORTFOLIO_BACKTEST = "portfolio_backtest"
    PORTFOLIO_CONSTRUCTION = "portfolio_construction"


@dataclass
class StrategyBacktestDetails:
    """Typspezifische Details eines Einzel-Asset-Strategie-Backtests."""

    order_executions: int
    closed_trades: int
    win_rate_percent: float
    profit_factor: float
    average_trade: float
    payoff_ratio: float


@dataclass
class PortfolioBacktestDetails:
    """Typspezifische Details eines Multi-Asset-Strategie-Backtests mit
    gemeinsamem Kapital."""

    order_executions: int
    closed_trades: int
    win_rate_percent: float
    profit_factor: float
    average_trade: float
    payoff_ratio: float
    allocation: dict[str, float]


@dataclass
class PortfolioConstructionDetails:
    """Typspezifische Details einer Portfolio-Construction-Simulation
    (Rebalancing, kein Strategy-System)."""

    rebalancing_orders: int
    rebalancing_count: int
    turnover_percent: float
    final_allocation: dict[str, float]


@dataclass
class ResearchReport:
    """Einheitlicher, quellen-unabhängiger Auswertungsbericht.

    Der Kern enthält nur equity-kurven-basierte Kennzahlen (identische
    Bedeutung, egal welche der drei Engines das Ergebnis erzeugt hat).
    `details` trägt alles Quellenspezifische, typisiert nach `source_type`.
    """

    name: str
    source_type: ResearchSourceType
    profit_loss: float
    performance_percent: float
    annualized_return_percent: float
    sharpe_ratio: float
    volatility_percent: float
    max_drawdown_percent: float
    calmar_ratio: float
    equity_curve: list[EquityPoint]
    details: StrategyBacktestDetails | PortfolioBacktestDetails | PortfolioConstructionDetails


def _trade_quality_fields(
    cycle_results: list[TradingCycleResult],
) -> tuple[int, float, float, float, float]:
    """Gemeinsame Berechnung der trade-basierten Kennzahlen für
    `StrategyBacktestDetails`/`PortfolioBacktestDetails` - beide nutzen
    dieselben `trade_ledger.py`-Funktionen auf denselben `ClosedTrade`-Daten.
    """

    closed_trades = extract_closed_trades(cycle_results)
    return (
        len(closed_trades),
        win_rate_percent(closed_trades),
        profit_factor(closed_trades),
        average_trade(closed_trades),
        payoff_ratio(closed_trades),
    )


def from_backtest_result(
    name: str,
    result: BacktestResult,
    periods_per_year: int,
) -> ResearchReport:
    """Erstellt einen `ResearchReport` aus einem Einzel-Asset-
    Strategie-Backtest (`BacktestResult` bleibt unverändert)."""

    initial_capital = infer_initial_capital(result)
    closed_count, win_rate, factor, avg_trade, payoff = _trade_quality_fields(
        result.cycle_results
    )

    return ResearchReport(
        name=name,
        source_type=ResearchSourceType.STRATEGY_BACKTEST,
        profit_loss=result.profit_loss,
        performance_percent=result.performance_percent,
        annualized_return_percent=annualized_return_percent(
            result.equity_curve, initial_capital, periods_per_year
        ),
        sharpe_ratio=sharpe_ratio(result.equity_curve, periods_per_year),
        volatility_percent=volatility_percent(result.equity_curve, periods_per_year),
        max_drawdown_percent=result.max_drawdown_percent,
        calmar_ratio=calmar_ratio(result.equity_curve, initial_capital, periods_per_year),
        equity_curve=result.equity_curve,
        details=StrategyBacktestDetails(
            order_executions=result.trades,
            closed_trades=closed_count,
            win_rate_percent=win_rate,
            profit_factor=factor,
            average_trade=avg_trade,
            payoff_ratio=payoff,
        ),
    )


def from_portfolio_backtest_result(
    name: str,
    result: PortfolioBacktestResult,
    periods_per_year: int,
) -> ResearchReport:
    """Erstellt einen `ResearchReport` aus einem Multi-Asset-Strategie-
    Backtest mit gemeinsamem Kapital (`PortfolioBacktestResult` bleibt
    unverändert)."""

    initial_capital = infer_initial_capital(result)
    all_cycles = [
        cycle for cycles in result.cycle_results_by_symbol.values() for cycle in cycles
    ]
    closed_count, win_rate, factor, avg_trade, payoff = _trade_quality_fields(all_cycles)

    return ResearchReport(
        name=name,
        source_type=ResearchSourceType.PORTFOLIO_BACKTEST,
        profit_loss=result.profit_loss,
        performance_percent=result.performance_percent,
        annualized_return_percent=annualized_return_percent(
            result.equity_curve, initial_capital, periods_per_year
        ),
        sharpe_ratio=sharpe_ratio(result.equity_curve, periods_per_year),
        volatility_percent=volatility_percent(result.equity_curve, periods_per_year),
        max_drawdown_percent=result.max_drawdown_percent,
        calmar_ratio=calmar_ratio(result.equity_curve, initial_capital, periods_per_year),
        equity_curve=result.equity_curve,
        details=PortfolioBacktestDetails(
            order_executions=result.trades,
            closed_trades=closed_count,
            win_rate_percent=win_rate,
            profit_factor=factor,
            average_trade=avg_trade,
            payoff_ratio=payoff,
            allocation=result.allocation,
        ),
    )


def _turnover_percent(result: PortfolioConstructionResult) -> float:
    """Durchschnittliches gehandeltes Volumen je Rebalancing-Ereignis, als
    Anteil (Prozent) des Portfolio-Werts.

    Lokale Kopie derselben Formel wie in `portfolio_construction_optimization.py`
    (dort privat) - bewusst nicht von dort importiert, um jene Datei nicht
    anzufassen.
    """

    if not result.rebalancing_events:
        return 0.0

    turnovers: list[float] = []
    for event in result.rebalancing_events:
        traded_value = sum(trade.quantity * trade.price for trade in event.trades)
        portfolio_value = result.equity_curve[event.step_index - 1].total_value
        if portfolio_value:
            turnovers.append(traded_value / portfolio_value * 100)

    if not turnovers:
        return 0.0

    return sum(turnovers) / len(turnovers)


def from_portfolio_construction_result(
    name: str,
    result: PortfolioConstructionResult,
    periods_per_year: int,
) -> ResearchReport:
    """Erstellt einen `ResearchReport` aus einer Portfolio-Construction-
    Simulation (`PortfolioConstructionResult` bleibt unverändert). Kein
    Strategy-System beteiligt - daher keine Win-Rate/Profit-Factor-Felder,
    sondern Rebalancing-eigene Kennzahlen in `PortfolioConstructionDetails`.
    """

    initial_capital = infer_initial_capital(result)
    final_allocation = result.allocation_history[-1] if result.allocation_history else {}

    return ResearchReport(
        name=name,
        source_type=ResearchSourceType.PORTFOLIO_CONSTRUCTION,
        profit_loss=result.profit_loss,
        performance_percent=result.performance_percent,
        annualized_return_percent=annualized_return_percent(
            result.equity_curve, initial_capital, periods_per_year
        ),
        sharpe_ratio=sharpe_ratio(result.equity_curve, periods_per_year),
        volatility_percent=volatility_percent(result.equity_curve, periods_per_year),
        max_drawdown_percent=result.max_drawdown_percent,
        calmar_ratio=calmar_ratio(result.equity_curve, initial_capital, periods_per_year),
        equity_curve=result.equity_curve,
        details=PortfolioConstructionDetails(
            rebalancing_orders=result.trades,
            rebalancing_count=len(result.rebalancing_events),
            turnover_percent=_turnover_percent(result),
            final_allocation=final_allocation,
        ),
    )


def compare_reports(reports: list[ResearchReport]) -> list[ResearchReport]:
    """Stellt mehrere Research-Reports nebeneinander, ohne nach einer
    Kennzahl zu sortieren (Reihenfolge wie übergeben).

    `ResearchReport` enthält bereits alle Kennzahlen (anders als
    `BacktestResult`, das erst über `rank_strategies()` in ein sortierbares
    `RankedResult` umgewandelt werden muss) - hier ist keine Umwandlung
    nötig. Die Funktion existiert für API-Symmetrie zu `rank_reports()` und
    als expliziter "keine Sortierung"-Einstiegspunkt.
    """

    return list(reports)


def rank_reports(
    reports: list[ResearchReport],
    sort_by: str = "sharpe_ratio",
) -> list[ResearchReport]:
    """Sortiert Research-Reports absteigend nach `sort_by`.

    Funktioniert unabhängig davon, aus welchem der drei Backtest-
    Ergebnistypen ein Report erzeugt wurde - alle nutzen dieselben, über
    `metrics.py` berechneten Kennzahlen. Das erlaubt erstmals einen fairen
    Vergleich z. B. eines Einzel-Strategie-Backtests gegen eine
    Portfolio-Construction-Simulation.

    Raises:
        AttributeError: wenn `sort_by` kein gültiges Feld von
            `ResearchReport` ist.
    """

    return sorted(reports, key=lambda report: getattr(report, sort_by), reverse=True)
