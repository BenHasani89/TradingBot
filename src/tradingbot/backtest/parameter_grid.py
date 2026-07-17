"""Generische Erzeugung von Strategie-Parameter-Varianten (Grid Search).

Enthält kein strategie-spezifisches Wissen: funktioniert für jede
`Strategy`-Unterklasse, deren Konstruktor einfache Schlüsselwort-Parameter
entgegennimmt. Reine Kombinatorik über die Standardbibliothek (`itertools`),
keine Optimierungslogik oder -bibliothek.
"""

from __future__ import annotations

from itertools import product
from typing import Any

from tradingbot.strategy.base import Strategy


def generate_parameter_grid(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Erzeugt alle Kombinationen eines Parameter-Grids (kartesisches Produkt).

    Args:
        param_grid: Zuordnung von Parametername zu Liste möglicher Werte,
            z. B. `{"short_window": [5, 10], "long_window": [20, 50]}`.

    Returns:
        Eine Liste von Parameter-Dictionaries, eines je Kombination. Ein
        leeres `param_grid` ergibt eine Liste mit einem leeren Dictionary
        (eine "Kombination ohne Parameter").
    """

    if not param_grid:
        return [{}]

    keys = list(param_grid.keys())
    value_lists = [param_grid[key] for key in keys]

    return [dict(zip(keys, combination, strict=True)) for combination in product(*value_lists)]


def build_strategy_variants(
    strategy_class: type[Strategy],
    param_grid: dict[str, list[Any]],
) -> dict[str, Strategy]:
    """Erzeugt eine benannte Strategie-Instanz je Parameter-Kombination.

    Instanziiert `strategy_class(**params)` für jede Kombination aus
    `generate_parameter_grid(param_grid)`. Funktioniert für jede Strategie,
    deren Konstruktor-Parameternamen den Grid-Schlüsseln entsprechen - diese
    Funktion selbst kennt keine konkrete Strategie.

    Returns:
        Zuordnung von automatisch generiertem, lesbarem Label
        (Klassenname + Parameter, z. B.
        `"MovingAverageCrossoverStrategy(short_window=5, long_window=20)"`)
        zur jeweiligen Strategie-Instanz - direkt verwendbar als
        `strategies`-Argument für `BacktestResearchRunner.run()`/`run_raw()`.
    """

    variants: dict[str, Strategy] = {}

    for params in generate_parameter_grid(param_grid):
        instance = strategy_class(**params)
        params_label = ", ".join(f"{key}={value}" for key, value in params.items())
        label = f"{strategy_class.__name__}({params_label})"
        variants[label] = instance

    return variants
