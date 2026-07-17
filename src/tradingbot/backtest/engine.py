"""Backtesting-Engine: spielt eine historische Kerzenserie über den
bestehenden TradingOrchestrator durch und wertet das Ergebnis aus.
"""

from __future__ import annotations

from loguru import logger

from tradingbot.backtest.metrics import max_drawdown_percent, performance_percent
from tradingbot.backtest.models import BacktestResult, EquityPoint
from tradingbot.core.models import TradingCycleResult
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.portfolio.manager import PortfolioManager


class BacktestEngine:
    """Spielt eine historische Kerzenserie bar-für-bar durch einen
    TradingOrchestrator durch.

    Bewusst unabhängig von einer konkreten Strategie: Welche Strategie zum
    Einsatz kommt, entscheidet ausschliesslich der übergebene
    `TradingOrchestrator` - die Engine kennt nur dessen `run_cycle()`-
    Schnittstelle, nicht die Strategie selbst.

    Vermeidet Look-Ahead-Bias, indem beim Schritt `i` ausschliesslich
    `candles[:i+1]` an den Orchestrator übergeben wird - nie mehr, als zu
    diesem Zeitpunkt bekannt wäre.
    """

    def __init__(
        self,
        orchestrator: TradingOrchestrator,
        portfolio: PortfolioManager,
        symbol: str,
        candles: list[MarketCandle],
    ) -> None:
        self._orchestrator = orchestrator
        self._portfolio = portfolio
        self._symbol = symbol
        self._candles = candles
        self._initial_capital = portfolio.status().capital

    def run(self) -> BacktestResult:
        """Führt den vollständigen Backtest aus und gibt das Ergebnis zurück.

        Iteriert chronologisch ab der zweitältesten Kerze (Index 1), damit
        der Strategie beim ersten Schritt bereits ein Zwei-Kerzen-Fenster
        vorliegt. Nach jedem Schritt wird der aktuelle Portfolio-Gesamtwert
        auf Basis des zu diesem Zeitpunkt bekannten Schlusskurses erfasst
        (Equity Curve).
        """

        cycle_results: list[TradingCycleResult] = []
        equity_curve: list[EquityPoint] = []

        for i in range(1, len(self._candles)):
            window = self._candles[: i + 1]
            result = self._orchestrator.run_cycle(window)
            cycle_results.append(result)

            current_candle = self._candles[i]
            total_value = self._portfolio.status().total_value(
                {self._symbol: current_candle.close}
            )
            equity_curve.append(
                EquityPoint(timestamp=current_candle.timestamp, total_value=total_value)
            )

        trades = sum(
            1
            for result in cycle_results
            if result.execution is not None and result.execution.success
        )
        final_value = (
            equity_curve[-1].total_value if equity_curve else self._initial_capital
        )

        logger.info(
            "Backtest abgeschlossen: {} Kerzen, {} Trades, Endwert {}",
            len(self._candles),
            trades,
            final_value,
        )

        return BacktestResult(
            trades=trades,
            profit_loss=final_value - self._initial_capital,
            performance_percent=performance_percent(self._initial_capital, equity_curve),
            max_drawdown_percent=max_drawdown_percent(equity_curve),
            equity_curve=equity_curve,
            cycle_results=cycle_results,
        )
