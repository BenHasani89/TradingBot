"""Research-Schicht: testet mehrere Strategien auf identischen historischen
Kerzen und stellt die Ergebnisse vergleichend gegenüber.
"""

from __future__ import annotations

from tradingbot.backtest.comparison import ComparisonRow, compare_strategies
from tradingbot.backtest.engine import BacktestEngine
from tradingbot.backtest.models import BacktestResult
from tradingbot.core.engine import TradingEngine
from tradingbot.core.orchestrator import TradingOrchestrator
from tradingbot.data.models import MarketCandle
from tradingbot.execution.broker import PaperBroker
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.manager import RiskManager
from tradingbot.strategy.base import Strategy


class BacktestResearchRunner:
    """Testet mehrere Strategien nacheinander auf denselben historischen
    Kerzen und vergleicht die Ergebnisse.

    Für jede Strategie wird ein komplett frisches Set aus `TradingEngine`,
    `RiskManager`, `PortfolioManager`, `PaperBroker` und `TradingOrchestrator`
    aufgebaut - so kann sich Zustand (Kapital, Positionen, Order-Historie)
    zwischen Strategien nicht überschneiden. Verwendet die bestehende
    `BacktestEngine` unverändert für jeden einzelnen Lauf und anschliessend
    `compare_strategies()` für die Gesamtauswertung.

    Keine Live-Börsen-Anbindung, keine Parameter-Optimierung - reine
    Auswertung bereits vorhandener Bausteine.
    """

    def __init__(
        self,
        candles: list[MarketCandle],
        initial_capital: float,
        risk_limit: float,
    ) -> None:
        self._candles = candles
        self._initial_capital = initial_capital
        self._risk_limit = risk_limit

    def run(self, strategies: dict[str, Strategy]) -> list[ComparisonRow]:
        """Führt für jede Strategie einen eigenen, isolierten Backtest aus.

        Args:
            strategies: Zuordnung von Strategie-Name zu Strategie-Instanz.
                Jede Instanz sollte frisch/unbenutzt übergeben werden, da
                manche Strategien (z. B. `BuyAndHoldStrategy`) internen
                Zustand über mehrere `analyze()`-Aufrufe hinweg führen.

        Returns:
            Eine Vergleichszeile je Strategie (über `compare_strategies()`),
            in derselben Reihenfolge wie `strategies`.
        """

        symbol = self._candles[0].symbol if self._candles else "UNKNOWN"
        results: dict[str, BacktestResult] = {}

        for name, strategy in strategies.items():
            engine = TradingEngine()
            engine.start()
            portfolio = PortfolioManager(initial_capital=self._initial_capital)
            orchestrator = TradingOrchestrator(
                engine=engine,
                strategy=strategy,
                risk_manager=RiskManager(max_position_size=self._risk_limit),
                portfolio=portfolio,
                broker=PaperBroker(),
            )
            backtest = BacktestEngine(
                orchestrator=orchestrator,
                portfolio=portfolio,
                symbol=symbol,
                candles=self._candles,
            )

            results[name] = backtest.run()

        return compare_strategies(results)
