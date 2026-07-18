"""Portfolio-Construction-Backtesting: eine RebalancingEngine gegen mehrere
synchronisierte Asset-Kerzenserien durchspielen.

Eigenständige Engine, komplett getrennt vom Strategy-System (kein
`Strategy`, kein `RiskManager`, kein `TradingOrchestrator` beteiligt) -
Rebalancing-Order-Absichten werden direkt über `PaperBroker`/
`PortfolioManager` ausgeführt. Kein Live-Trading, keine Börsen-Anbindung,
keine externen Bibliotheken.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.backtest.metrics import max_drawdown_percent, performance_percent
from tradingbot.backtest.models import EquityPoint
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import PaperBroker
from tradingbot.execution.models import Order
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.portfolio_construction.models import RebalancingEvent
from tradingbot.portfolio_construction.rebalancing import RebalancingEngine


@dataclass
class PortfolioConstructionResult:
    """Ergebnis einer Portfolio-Construction-Backtest-Simulation.

    Analog zu `PortfolioBacktestResult`, aber ohne `cycle_results_by_symbol`
    (kein Strategy-System beteiligt) - stattdessen `rebalancing_events` und
    `allocation_history` (die von der Policy berechneten Ziel-Gewichte zu
    jedem Zeitschritt, unabhängig davon, ob tatsächlich rebalanciert wurde).
    `equity_curve_by_symbol` enthält hier reine Positionswerte (kein
    notionales Sub-Cash wie bei `PortfolioBacktestEngine`, da es keine feste
    Start-Allokation gibt, gegen die sich das sinnvoll verrechnen liesse -
    die Zielgewichte ändern sich pro Zeitschritt).
    """

    trades: int
    profit_loss: float
    performance_percent: float
    max_drawdown_percent: float
    equity_curve: list[EquityPoint]
    equity_curve_by_symbol: dict[str, list[EquityPoint]]
    allocation_history: list[dict[str, float]]
    rebalancing_events: list[RebalancingEvent]


class PortfolioConstructionEngine:
    """Simuliert eine `RebalancingEngine` über mehrere Assets hinweg, mit
    einem gemeinsamen `PortfolioManager`/`PaperBroker`.

    Die Kerzenserien müssen gleich lang und zeitlich ausgerichtet sein -
    bei unterschiedlichen Längen wird nur bis zur kürzesten Serie simuliert
    (gleiche Konvention wie `PortfolioBacktestEngine`).
    """

    def __init__(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        rebalancing_engine: RebalancingEngine,
        initial_capital: float,
    ) -> None:
        self._candles_by_symbol = candles_by_symbol
        self._rebalancing_engine = rebalancing_engine
        self._initial_capital = initial_capital

    def run(self) -> PortfolioConstructionResult:
        """Führt die synchronisierte Simulation aus.

        Gibt ein Ergebnis mit leeren Zeitreihen zurück (keine Ausnahme),
        wenn keine Kerzenserien übergeben wurden oder diese zu kurz für
        auch nur einen synchronisierten Zeitschritt sind.
        """

        symbols = list(self._candles_by_symbol.keys())
        portfolio = PortfolioManager(initial_capital=self._initial_capital)
        broker = PaperBroker()

        step_count = min((len(c) for c in self._candles_by_symbol.values()), default=0)
        equity_curve: list[EquityPoint] = []
        equity_curve_by_symbol: dict[str, list[EquityPoint]] = {symbol: [] for symbol in symbols}
        allocation_history: list[dict[str, float]] = []
        rebalancing_events: list[RebalancingEvent] = []
        executed_order_count = 0

        for i in range(1, step_count):
            windowed_candles = {
                symbol: self._candles_by_symbol[symbol][: i + 1] for symbol in symbols
            }
            current_prices = {symbol: windowed_candles[symbol][-1].close for symbol in symbols}
            timestamp = self._candles_by_symbol[symbols[0]][i].timestamp

            target_weights = self._rebalancing_engine.policy.target_weights(
                windowed_candles, portfolio.status()
            )
            allocation_history.append(target_weights)

            rebalancing_trades = self._rebalancing_engine.generate_rebalancing_orders(
                candles_by_symbol=windowed_candles,
                current_prices=current_prices,
                portfolio_status=portfolio.status(),
                step_index=i,
            )

            executed_trades = []
            for rebalancing_trade in rebalancing_trades:
                order = Order(
                    symbol=rebalancing_trade.symbol,
                    side=rebalancing_trade.side,
                    quantity=rebalancing_trade.quantity,
                    price=rebalancing_trade.price,
                )
                execution = broker.execute(order)
                if execution.success:
                    portfolio.apply_trade(
                        symbol=execution.order.symbol,
                        side=execution.order.side,
                        quantity=execution.order.quantity,
                        price=execution.order.price,
                    )
                    executed_trades.append(rebalancing_trade)
                    executed_order_count += 1

            if executed_trades:
                rebalancing_events.append(
                    RebalancingEvent(
                        step_index=i,
                        timestamp=timestamp,
                        target_weights=target_weights,
                        trades=executed_trades,
                    )
                )

            total_value = portfolio.status().total_value(current_prices)
            equity_curve.append(EquityPoint(timestamp=timestamp, total_value=total_value))

            positions_by_symbol = {p.symbol: p for p in portfolio.status().positions}
            for symbol in symbols:
                position = positions_by_symbol.get(symbol)
                position_value = position.value(current_prices[symbol]) if position else 0.0
                equity_curve_by_symbol[symbol].append(
                    EquityPoint(timestamp=timestamp, total_value=position_value)
                )

        final_value = equity_curve[-1].total_value if equity_curve else self._initial_capital

        return PortfolioConstructionResult(
            trades=executed_order_count,
            profit_loss=final_value - self._initial_capital,
            performance_percent=performance_percent(self._initial_capital, equity_curve),
            max_drawdown_percent=max_drawdown_percent(equity_curve),
            equity_curve=equity_curve,
            equity_curve_by_symbol=equity_curve_by_symbol,
            allocation_history=allocation_history,
            rebalancing_events=rebalancing_events,
        )
