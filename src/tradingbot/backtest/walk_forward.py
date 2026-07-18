"""Walk-Forward-Testing: Parameter-Optimierung auf expandierenden
In-Sample-Fenstern mit automatischem Out-of-Sample-Test der Gewinnerstrategie.

Reine Orchestrierung bereits vorhandener Bausteine (`BacktestResearchRunner`,
`parameter_grid.build_strategy_variants`, `optimization.rank_strategies`) -
keine neue Backtest- oder Strategie-Logik, keine externen Bibliotheken.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradingbot.backtest.optimization import RankedResult, rank_strategies
from tradingbot.backtest.parameter_grid import build_strategy_variants
from tradingbot.backtest.research import BacktestResearchRunner
from tradingbot.data.models import MarketCandle
from tradingbot.strategy.base import Strategy


@dataclass
class WalkForwardWindow:
    """Ein Trainings-/Testfenster für Walk-Forward-Testing."""

    window_index: int
    in_sample: list[MarketCandle]
    out_of_sample: list[MarketCandle]


@dataclass
class WalkForwardWindowResult:
    """Ergebnis eines einzelnen Walk-Forward-Fensters.

    `in_sample_ranking` enthält alle getesteten Parameter-Varianten
    (absteigend sortiert), `out_of_sample_result` ausschliesslich die
    Auswertung der Gewinnerstrategie (`winning_strategy_name`) auf den
    Out-of-Sample-Kerzen dieses Fensters.
    """

    window_index: int
    winning_strategy_name: str
    in_sample_ranking: list[RankedResult]
    out_of_sample_result: RankedResult


def generate_walk_forward_windows(
    candles: list[MarketCandle],
    initial_train_size: int,
    out_of_sample_size: int,
) -> list[WalkForwardWindow]:
    """Erzeugt expandierende Walk-Forward-Fenster.

    Das Trainingsfenster wächst mit jedem Schritt (immer ab Index 0), das
    Testfenster hat stets `out_of_sample_size` Kerzen direkt danach. Die
    Schrittweite zwischen aufeinanderfolgenden Fenstern entspricht immer
    `out_of_sample_size`, sodass die Testfenster über alle Fenster hinweg
    lückenlos und überlappungsfrei aneinander anschliessen.

    Beispiel bei `initial_train_size=200, out_of_sample_size=50`:
    Train 0-200/Test 200-250, danach Train 0-250/Test 250-300, danach
    Train 0-300/Test 300-350, ...

    Liefert eine leere Liste (keine Ausnahme), wenn nicht einmal ein
    vollständiges erstes Fenster in `candles` passt, oder wenn
    `out_of_sample_size <= 0` ist (würde sonst nie terminieren, da sich das
    Trainingsfenster dann nicht vergrössert).
    """

    if out_of_sample_size <= 0:
        return []

    windows: list[WalkForwardWindow] = []
    train_end = initial_train_size
    window_index = 0

    while train_end + out_of_sample_size <= len(candles):
        windows.append(
            WalkForwardWindow(
                window_index=window_index,
                in_sample=candles[:train_end],
                out_of_sample=candles[train_end : train_end + out_of_sample_size],
            )
        )
        train_end += out_of_sample_size
        window_index += 1

    return windows


class WalkForwardRunner:
    """Führt Walk-Forward-Testing für eine Strategie-Klasse über ein
    Parameter-Grid aus.

    Pro Fenster: Parameter-Varianten werden ausschliesslich auf dem
    In-Sample-Abschnitt gerankt (`optimization.rank_strategies`), die
    Gewinnerstrategie wird als **frische Instanz** (nie die im In-Sample-
    Schritt bereits verwendete) auf dem Out-of-Sample-Abschnitt getestet.
    Kein Live-Trading, keine echten Börsendaten, keine ML-Optimierung -
    ausschliesslich Grid Search + Ranking auf bereits vorhandenen,
    unveränderten Bausteinen (`BacktestResearchRunner`, `BacktestEngine`).
    """

    def __init__(
        self,
        candles: list[MarketCandle],
        strategy_class: type[Strategy],
        param_grid: dict[str, list[Any]],
        initial_capital: float,
        risk_limit: float,
        periods_per_year: int,
        initial_train_size: int,
        out_of_sample_size: int,
        sort_by: str = "sharpe_ratio",
    ) -> None:
        self._candles = candles
        self._strategy_class = strategy_class
        self._param_grid = param_grid
        self._initial_capital = initial_capital
        self._risk_limit = risk_limit
        self._periods_per_year = periods_per_year
        self._initial_train_size = initial_train_size
        self._out_of_sample_size = out_of_sample_size
        self._sort_by = sort_by

    def run(self) -> list[WalkForwardWindowResult]:
        """Führt Walk-Forward-Testing über alle Fenster aus.

        Liefert eine leere Liste (keine Ausnahme), wenn die historischen
        Kerzen nicht für mindestens ein vollständiges Fenster ausreichen.
        """

        windows = generate_walk_forward_windows(
            self._candles, self._initial_train_size, self._out_of_sample_size
        )

        results: list[WalkForwardWindowResult] = []

        for window in windows:
            in_sample_ranking = self._rank_in_sample(window)
            if not in_sample_ranking:
                continue

            winner_name = in_sample_ranking[0].strategy_name
            out_of_sample_result = self._evaluate_out_of_sample(window, winner_name)

            results.append(
                WalkForwardWindowResult(
                    window_index=window.window_index,
                    winning_strategy_name=winner_name,
                    in_sample_ranking=in_sample_ranking,
                    out_of_sample_result=out_of_sample_result,
                )
            )

        return results

    def _rank_in_sample(self, window: WalkForwardWindow) -> list[RankedResult]:
        variants = build_strategy_variants(self._strategy_class, self._param_grid)
        runner = BacktestResearchRunner(
            candles=window.in_sample,
            initial_capital=self._initial_capital,
            risk_limit=self._risk_limit,
        )
        raw_results = runner.run_raw(variants)
        return rank_strategies(raw_results, self._periods_per_year, sort_by=self._sort_by)

    def _evaluate_out_of_sample(
        self,
        window: WalkForwardWindow,
        winner_name: str,
    ) -> RankedResult:
        # Zweiter, unabhängiger Aufruf: build_strategy_variants ist eine reine
        # Funktion und liefert bei gleichem Grid dieselben Labels, aber
        # FRISCHE Instanzen - wichtig, da Strategien Zustand tragen können
        # (z. B. BuyAndHoldStrategy) und die im In-Sample-Schritt bereits
        # verwendete Instanz nicht unverändert weiterverwendet werden darf.
        fresh_variants = build_strategy_variants(self._strategy_class, self._param_grid)
        winner_strategy = fresh_variants[winner_name]

        runner = BacktestResearchRunner(
            candles=window.out_of_sample,
            initial_capital=self._initial_capital,
            risk_limit=self._risk_limit,
        )
        # Ausschliesslich die Gewinnerstrategie wird auf Out-of-Sample-Daten
        # ausgeführt - alle anderen Varianten dieser frischen Instanziierung
        # werden verworfen, ohne je aufgerufen zu werden.
        raw_results = runner.run_raw({winner_name: winner_strategy})

        return rank_strategies(raw_results, self._periods_per_year)[0]
