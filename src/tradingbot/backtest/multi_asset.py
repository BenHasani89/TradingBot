"""Multi-Asset-Research: dieselbe Strategie(-Parametrisierung) über mehrere
Symbole hinweg testen, mit isolierten, frischen Strategie-Instanzen je Asset.

Reine Orchestrierung bereits vorhandener Bausteine (`DataProvider`,
`BacktestResearchRunner`) - keine neue Backtest- oder Strategie-Logik, keine
externen Bibliotheken, keine Börsen-Anbindung.
"""

from __future__ import annotations

from typing import Any

from tradingbot.backtest.models import BacktestResult
from tradingbot.backtest.research import BacktestResearchRunner
from tradingbot.data.models import MarketCandle
from tradingbot.data.provider import DataProvider
from tradingbot.strategy.base import Strategy


def fetch_multi_asset_candles(
    provider: DataProvider,
    symbols: list[str],
    timeframe: str,
    limit: int,
) -> dict[str, list[MarketCandle]]:
    """Ruft historische Kerzen für mehrere Symbole vom selben Provider ab.

    Ein `get_candles()`-Aufruf je Symbol - keine eigene Abruf- oder
    Cache-Logik.
    """

    return {symbol: provider.get_candles(symbol, timeframe, limit) for symbol in symbols}


class MultiAssetResearchRunner:
    """Testet dieselbe Strategie-Parametrisierung über mehrere Assets.

    Baut für jedes Symbol eine **frische** Strategie-Instanz (Zustands-
    Isolation zwischen Assets - dasselbe Prinzip wie bereits bei
    `WalkForwardRunner` zwischen Zeitfenstern) und delegiert die eigentliche
    Ausführung unverändert an `BacktestResearchRunner`.
    """

    def __init__(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
        initial_capital: float,
        risk_limit: float,
    ) -> None:
        self._candles_by_symbol = candles_by_symbol
        self._initial_capital = initial_capital
        self._risk_limit = risk_limit

    def run(
        self,
        strategy_class: type[Strategy],
        strategy_params: dict[str, Any],
    ) -> dict[str, BacktestResult]:
        """Führt für jedes Asset einen isolierten Backtest mit derselben
        Strategie-Parametrisierung aus.

        Args:
            strategy_class: Strategie-Klasse, wird pro Asset frisch
                instanziiert (`strategy_class(**strategy_params)`).
            strategy_params: Konstruktor-Parameter, identisch für alle
                Assets - Voraussetzung für einen fairen Vergleich. Die
                Strategie darf das Symbol daher nicht als fixen
                Konstruktor-Parameter erwarten, sondern muss es (wie
                `MovingAverageCrossoverStrategy`) aus den übergebenen Kerzen
                lesen.

        Returns:
            Zuordnung von Symbol zu `BacktestResult`.
        """

        results: dict[str, BacktestResult] = {}

        for symbol, candles in self._candles_by_symbol.items():
            strategy = strategy_class(**strategy_params)
            runner = BacktestResearchRunner(
                candles=candles,
                initial_capital=self._initial_capital,
                risk_limit=self._risk_limit,
            )
            raw_results = runner.run_raw({symbol: strategy})
            results[symbol] = raw_results[symbol]

        return results
