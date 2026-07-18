"""Portfolio-Backtesting: mehrere Asset-Kerzenserien synchron durch ein
gemeinsames Portfolio simulieren.

Neue, eigenständige Ablaufschicht - ersetzt `BacktestEngine` nicht (bleibt
für Einzel-Asset-Backtests unverändert bestehen), sondern ergänzt sie um
echtes gemeinsames Kapital über mehrere Assets. Verwendet
`TradingOrchestrator.run_cycle()` unverändert, mehrfach instanziiert mit
geteiltem `PortfolioManager`/`PaperBroker`/`TradingEngine`, aber je Asset
eigener Strategie- und `RiskManager`-Instanz (Kapitalallokation, siehe
`capital_allocation.py`). Keine externen Bibliotheken, keine Börsen-Anbindung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradingbot.backtest.capital_allocation import CapitalAllocator
from tradingbot.backtest.metrics import max_drawdown_percent, performance_percent
from tradingbot.backtest.models import EquityPoint
from tradingbot.core.engine import TradingEngine
from tradingbot.core.models import TradingCycleResult
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import PaperBroker
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.base import Strategy


@dataclass
class PortfolioBacktestResult:
    """Ergebnis einer Portfolio-Backtest-Simulation über mehrere Assets."""

    trades: int
    profit_loss: float
    performance_percent: float
    max_drawdown_percent: float
    equity_curve: list[EquityPoint]
    cycle_results_by_symbol: dict[str, list[TradingCycleResult]]
    allocation: dict[str, float]


class PortfolioBacktestEngine:
    """Simuliert ein gemeinsames Portfolio über mehrere Assets hinweg.

    Alle Assets teilen sich EIN `PortfolioManager`, EIN `PaperBroker` und
    EINE `TradingEngine` - ein gemeinsamer Kapitaltopf statt getrennter
    Konten. Jedes Asset bekommt eine frische Strategie-Instanz sowie einen
    eigenen `RiskManager`, dessen `max_position_size` fest auf den über
    `CapitalAllocator` zugeteilten Kapitalanteil begrenzt ist - so kann kein
    Asset in einer einzelnen Order mehr als seinen zugeteilten Anteil
    beanspruchen. Die Kapitalprüfung selbst (Kapital wird nie negativ) kommt
    unverändert aus `TradingOrchestrator.run_cycle()`.

    Die Kerzenserien müssen gleich lang und zeitlich ausgerichtet sein
    (gleicher Zeitrahmen, gleiche Anzahl Kerzen) - bei unterschiedlichen
    Längen wird nur bis zur kürzesten Serie simuliert.
    """

    def __init__(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        strategy_class: type[Strategy],
        strategy_params: dict[str, Any],
        initial_capital: float,
        allocator: CapitalAllocator,
    ) -> None:
        self._candles_by_symbol = candles_by_symbol
        self._strategy_class = strategy_class
        self._strategy_params = strategy_params
        self._initial_capital = initial_capital
        self._allocator = allocator

    def run(self) -> PortfolioBacktestResult:
        """Führt die synchronisierte Portfolio-Simulation aus.

        Gibt ein Ergebnis mit leerer Equity-Kurve zurück (keine Ausnahme),
        wenn keine Kerzenserien übergeben wurden oder diese zu kurz für
        auch nur einen synchronisierten Zeitschritt sind.
        """

        symbols = list(self._candles_by_symbol.keys())
        allocation = self._allocator.allocation_for(symbols, self._initial_capital)

        engine = TradingEngine()
        engine.start()
        portfolio = PortfolioManager(initial_capital=self._initial_capital)
        broker = PaperBroker()

        orchestrators = {
            symbol: TradingOrchestrator(
                engine=engine,
                strategy=self._strategy_class(**self._strategy_params),
                risk_manager=RiskManager(max_position_size=allocation[symbol]),
                portfolio=portfolio,
                broker=broker,
            )
            for symbol in symbols
        }

        step_count = min((len(c) for c in self._candles_by_symbol.values()), default=0)
        cycle_results_by_symbol: dict[str, list[TradingCycleResult]] = {
            symbol: [] for symbol in symbols
        }
        equity_curve: list[EquityPoint] = []

        for i in range(1, step_count):
            current_prices: dict[str, float] = {}

            for symbol in symbols:
                window = self._candles_by_symbol[symbol][: i + 1]
                result = orchestrators[symbol].run_cycle(window)
                cycle_results_by_symbol[symbol].append(result)
                current_prices[symbol] = window[-1].close

            timestamp = self._candles_by_symbol[symbols[0]][i].timestamp
            total_value = portfolio.status().total_value(current_prices)
            equity_curve.append(EquityPoint(timestamp=timestamp, total_value=total_value))

        trades = sum(
            1
            for cycles in cycle_results_by_symbol.values()
            for cycle in cycles
            if cycle.execution is not None and cycle.execution.success
        )
        final_value = equity_curve[-1].total_value if equity_curve else self._initial_capital

        return PortfolioBacktestResult(
            trades=trades,
            profit_loss=final_value - self._initial_capital,
            performance_percent=performance_percent(self._initial_capital, equity_curve),
            max_drawdown_percent=max_drawdown_percent(equity_curve),
            equity_curve=equity_curve,
            cycle_results_by_symbol=cycle_results_by_symbol,
            allocation=allocation,
        )
